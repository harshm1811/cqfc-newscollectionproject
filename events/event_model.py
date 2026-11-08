"""
events/event_model.py - Data contracts for Group 3 / Person 1.

Plain dataclasses (no heavy dependencies) so they can be serialised with
`to_dict()` and consumed by Person 2/3 (importance, decay, quant features).

Flow:   RawArticleRecord (Group 1/2)  ->  Article
        Article[]  --clusterer-->  Event[] + ArticleEventMapping[]
        Event  --classifier-->  event_type
        Article/Event  --sentiment-->  probabilities + sentiment_score
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field, asdict
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Dict, List, Optional


class EventType(str, Enum):
    EARNINGS = "EARNINGS"
    GUIDANCE = "GUIDANCE"
    MERGER_ACQUISITION = "MERGER_ACQUISITION"
    DIVIDEND = "DIVIDEND"
    BUYBACK = "BUYBACK"
    CAPITAL_RAISE = "CAPITAL_RAISE"
    DEBT_FINANCING = "DEBT_FINANCING"
    MANAGEMENT_CHANGE = "MANAGEMENT_CHANGE"
    PRODUCT_SERVICE = "PRODUCT_SERVICE"
    EXPANSION = "EXPANSION"
    CAPEX = "CAPEX"
    MAJOR_CONTRACT = "MAJOR_CONTRACT"
    REGULATION = "REGULATION"
    LITIGATION = "LITIGATION"
    INVESTIGATION = "INVESTIGATION"
    FRAUD = "FRAUD"
    ANALYST_ACTION = "ANALYST_ACTION"
    SUBSIDIARY_EVENT = "SUBSIDIARY_EVENT"
    CORPORATE_ACTION = "CORPORATE_ACTION"
    OTHER = "OTHER"


def parse_iso(ts: Optional[str]) -> Optional[datetime]:
    """Parse an ISO-8601 string into a timezone-aware UTC datetime."""
    if not ts:
        return None
    try:
        dt = datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except ValueError:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def make_article_id(url: str, ticker: str = "") -> str:
    return "ART-" + hashlib.sha1(f"{ticker.upper()}|{url}".encode("utf-8")).hexdigest()[:12]


@dataclass
class SentimentResult:
    """Probabilities are ALWAYS kept; score = P(pos) - P(neg) in [-1, 1]."""
    positive_probability: float
    neutral_probability: float
    negative_probability: float
    sentiment_score: float
    model_name: str = ""

    @staticmethod
    def from_probs(pos: float, neu: float, neg: float, model_name: str = "") -> "SentimentResult":
        total = pos + neu + neg
        if total <= 0:
            pos, neu, neg, total = 0.0, 1.0, 0.0, 1.0
        pos, neu, neg = pos / total, neu / total, neg / total
        return SentimentResult(pos, neu, neg, pos - neg, model_name)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Article:
    """Group-3 view of a RawArticleRecord."""
    article_id: str
    ticker: str
    company_name: str
    title: str
    description: str
    url: str
    source: str
    source_type: str
    primary_source: bool
    published_at: Optional[datetime]
    first_seen_at: Optional[datetime]
    sentiment: Optional[SentimentResult] = None

    @property
    def text(self) -> str:
        if self.description:
            return f"{self.title}. {self.description}"
        return self.title

    @property
    def timestamp(self) -> datetime:
        """Best available time: published_at, else first_seen_at, else epoch."""
        return self.published_at or self.first_seen_at or datetime(1970, 1, 1, tzinfo=timezone.utc)

    @classmethod
    def from_raw(cls, raw: Any) -> "Article":
        """Accepts a RawArticleRecord, a dict, or any object with the same attributes."""
        if isinstance(raw, dict):
            g = lambda k, d=None: raw.get(k, d)  # noqa: E731
        else:
            g = lambda k, d=None: getattr(raw, k, d)  # noqa: E731
        url, ticker = g("url", "") or "", g("ticker", "") or ""
        return cls(
            article_id=make_article_id(url, ticker),
            ticker=ticker.upper(),
            company_name=g("company_name", "") or "",
            title=(g("title", "") or "").strip(),
            description=(g("description", "") or "").strip(),
            url=url,
            source=g("source", "") or "",
            source_type=g("source_type", "") or "",
            primary_source=bool(g("primary_source", False)),
            published_at=parse_iso(g("published_at")),
            first_seen_at=parse_iso(g("first_seen_at")),
        )

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat() if self.published_at else None
        d["first_seen_at"] = self.first_seen_at.isoformat() if self.first_seen_at else None
        return d


@dataclass
class ArticleEventMapping:
    """ARTICLE -> EVENT mapping row."""
    article_id: str
    event_id: str
    similarity: float = 1.0   # similarity to the cluster at assignment time

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Event:
    event_id: str
    ticker: str
    title: str                              # representative headline
    article_ids: List[str] = field(default_factory=list)
    first_article_at: Optional[datetime] = None
    last_article_at: Optional[datetime] = None
    event_type: EventType = EventType.OTHER
    type_confidence: float = 0.0
    type_scores: Dict[str, float] = field(default_factory=dict)

    # Event-level sentiment (probabilities are never discarded)
    positive_probability: Optional[float] = None
    neutral_probability: Optional[float] = None
    negative_probability: Optional[float] = None
    sentiment_score: Optional[float] = None

    # Counts exposed for Person 2/3 (importance / source agreement)
    article_count: int = 0
    independent_source_count: int = 0
    primary_source_confirmed: bool = False

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value
        d["first_article_at"] = self.first_article_at.isoformat() if self.first_article_at else None
        d["last_article_at"] = self.last_article_at.isoformat() if self.last_article_at else None
        return d
