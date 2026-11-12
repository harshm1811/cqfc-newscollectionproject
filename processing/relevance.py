"""
processing/relevance.py - Configurable Equity Relevance Engine.

Evaluates whether an article contains meaningful, actionable information
concerning the target equity.
Signals:
- Ticker occurrence in title vs body
- Company canonical name & aliases in title vs body
- Subsidiary / brand mentions
- Financial keywords and event context (earnings, revenue, capex, contracts, litigation, etc.)
- Entity mention frequency & density
- Proximity between entity and financial keywords
- Configurable relevance threshold filtering
"""

from __future__ import annotations

import math
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

FINANCIAL_ACTION_KEYWORDS = {
    # Earnings & Performance
    "earnings", "profit", "net profit", "ebitda", "revenue", "loss", "margin", "quarterly results",
    "q1", "q2", "q3", "q4", "fy24", "fy25", "fy26", "topline", "bottomline",
    # M&A & Expansion
    "acquisition", "acquires", "merger", "stake", "buyout", "expansion", "capex", "investment",
    "joint venture", "jv", "subsidiary", "deal", "contract", "order win",
    # Capital actions
    "dividend", "buyback", "share repurchase", "rights issue", "qip", "fpo", "ipo", "debt",
    "bond", "credit rating", "fundraising",
    # Regulatory & Governance
    "sebi", "rbi", "nclt", "investigation", "litigation", "court", "probe", "show cause",
    "ceo", "cfo", "board", "resignation", "appointment", "compliance",
    # Business & Product
    "launches", "unveils", "5g", "ai", "platform", "tariffs", "patent",
}

PASSING_MENTION_INDICATORS = {
    "attended", "conference", "panel", "seminar", "among peers", "market roundup",
    "sensex", "nifty", "broader market", "top gainers", "top losers",
}


class RelevanceEngine:
    """Configurable equity relevance scoring engine."""

    def __init__(
        self,
        min_relevance_threshold: float = 0.50,
        title_weight: float = 0.50,
        body_weight: float = 0.30,
        financial_keyword_weight: float = 0.20,
    ):
        self.min_relevance_threshold = min_relevance_threshold
        self.title_weight = title_weight
        self.body_weight = body_weight
        self.financial_keyword_weight = financial_keyword_weight

    def score_record(
        self,
        article: Dict[str, Any],
        company_profile: Optional[Dict[str, Any]] = None,
    ) -> float:
        """
        Calculate an equity relevance score between 0.0 and 1.0.
        """
        title = str(article.get("title") or "").lower()
        clean_text = str(article.get("clean_text") or article.get("description") or "").lower()

        # Build profile if not supplied explicitly
        if not company_profile:
            company_profile = {
                "name": str(article.get("company_name") or ""),
                "ticker": str(article.get("ticker") or ""),
                "aliases": article.get("aliases", []),
                "subsidiaries": article.get("subsidiaries", []),
            }

        ticker = str(company_profile.get("ticker") or "").strip().lower()
        name = str(company_profile.get("name") or "").strip().lower()
        aliases = [str(a).strip().lower() for a in (company_profile.get("aliases") or []) if a]
        subsidiaries = [str(s).strip().lower() for s in (company_profile.get("subsidiaries") or []) if s]

        # All entity names to search for
        entities = [e for e in [name] + aliases if e]

        # 1. Headline Presence
        title_entity_score = 0.0
        if ticker and re.search(rf"\b{re.escape(ticker)}\b", title):
            title_entity_score = max(title_entity_score, 0.95)
        for ent in entities:
            if re.search(rf"\b{re.escape(ent)}\b", title):
                title_entity_score = max(title_entity_score, 1.0)
                break
        for sub in subsidiaries:
            if re.search(rf"\b{re.escape(sub)}\b", title):
                title_entity_score = max(title_entity_score, 0.85)
                break

        # 2. Body / Text Presence & Frequency
        body_entity_count = 0
        if ticker:
            body_entity_count += len(re.findall(rf"\b{re.escape(ticker)}\b", clean_text))
        for ent in entities:
            body_entity_count += len(re.findall(rf"\b{re.escape(ent)}\b", clean_text))
        for sub in subsidiaries:
            body_entity_count += len(re.findall(rf"\b{re.escape(sub)}\b", clean_text))

        # Density score (saturates at 5 mentions)
        body_entity_score = min(1.0, body_entity_count / 3.0) if body_entity_count > 0 else 0.0

        # 3. Financial Action Keywords Context
        fin_matches_title = sum(1 for kw in FINANCIAL_ACTION_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", title))
        fin_matches_body = sum(1 for kw in FINANCIAL_ACTION_KEYWORDS if re.search(rf"\b{re.escape(kw)}\b", clean_text))

        fin_score = min(1.0, (fin_matches_title * 0.4) + (fin_matches_body * 0.15))

        # 4. Entity Proximity / Core Focus Check
        # If entity only appears once in a long article along with passing indicators
        passing_mention = any(ind in title or ind in clean_text for ind in PASSING_MENTION_INDICATORS)
        is_diluted = body_entity_count == 1 and passing_mention and not title_entity_score

        # Composite score
        if title_entity_score >= 0.85 and fin_score >= 0.3:
            # Clear headline focus on company + financial event (e.g. Reliance profit jumps 16%)
            raw_score = 0.90 + (0.10 * fin_score)
        elif title_entity_score >= 0.85:
            # In headline, generic focus
            raw_score = 0.80 + (0.15 * body_entity_score)
        elif body_entity_score > 0 and fin_score > 0:
            raw_score = (0.50 * body_entity_score) + (0.35 * fin_score)
        elif body_entity_score > 0:
            raw_score = 0.35 * body_entity_score
        else:
            raw_score = 0.05

        if is_diluted:
            raw_score = min(raw_score, 0.25)

        return round(float(max(0.0, min(1.0, raw_score))), 2)

    def filter_relevant(
        self,
        articles: Sequence[Dict[str, Any]],
        threshold: Optional[float] = None,
    ) -> Tuple[List[Dict[str, Any]], List[Dict[str, Any]]]:
        """
        Partition articles into (relevant, excluded) lists based on configurable threshold.
        """
        th = threshold if threshold is not None else self.min_relevance_threshold
        relevant = []
        excluded = []
        for art in articles:
            score = art.get("relevance_score")
            if score is None:
                score = self.score_record(art)
                art["relevance_score"] = score
            if score >= th:
                relevant.append(art)
            else:
                excluded.append(art)
        return relevant, excluded


# Standalone function for backward compatibility
def calculate_relevance_score(
    news_record: Dict[str, Any],
    company_profile: Optional[Dict[str, Any]] = None,
) -> float:
    engine = RelevanceEngine()
    return engine.score_record(news_record, company_profile)
