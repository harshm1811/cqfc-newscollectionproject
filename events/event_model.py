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
import math
from collections.abc import Mapping
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


def parse_iso(ts: Any) -> Optional[datetime]:
    """Parse an ISO timestamp or datetime as UTC.

    Naive datetimes and timestamps without an offset are assumed to be UTC,
    matching the Group 2 ingestion contract. Missing or blank values stay None;
    malformed nonblank values raise ValueError rather than disappearing.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str):
        value = ts.strip()
        if not value:
            return None
        if value.endswith(("Z", "z")):
            value = value[:-1] + "+00:00"
        try:
            dt = datetime.fromisoformat(value)
        except ValueError as exc:
            raise ValueError(f"Invalid ISO-8601 timestamp: {ts!r}") from exc
    else:
        raise TypeError(f"Timestamp must be an ISO-8601 string, datetime, or None; got {type(ts).__name__}")
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
        values = [float(pos), float(neu), float(neg)]
        if any(not math.isfinite(value) or value < 0 for value in values):
            raise ValueError("sentiment probabilities must be finite and non-negative")
        pos, neu, neg = values
        total = pos + neu + neg
        if total <= 0:
            raise ValueError("at least one sentiment probability must be positive")
        pos, neu, neg = pos / total, neu / total, neg / total
        return SentimentResult(pos, neu, neg, pos - neg, model_name)

    def to_dict(self) -> Dict[str, Any]:
        return asdict(self)


@dataclass
class Article:
    """Group-3 view of a Clean Article Record (from Group 2)."""
    article_id: str
    ticker: str
    company_name: str
    title: str
    clean_text: str = ""
    description: str = ""
    url: str = ""
    source: str = ""
    source_type: str = ""
    primary_source: bool = False
    independent_source: Optional[bool] = None
    independent_source_id: Optional[str] = None
    relevance_score: Optional[float] = None
    duplicate_cluster_id: Optional[str] = None
    published_at: Optional[datetime] = None
    first_seen_at: Optional[datetime] = None
    sentiment: Optional[SentimentResult] = None

    @property
    def text(self) -> str:
        body = self.clean_text or self.description
        if body:
            return f"{self.title}. {body}" if self.title not in body else body
        return self.title

    @property
    def timestamp(self) -> Optional[datetime]:
        """Best observed time, or None when Group 2 supplied no usable timestamp."""
        return self.published_at or self.first_seen_at

    @classmethod
    def from_raw(cls, raw: Any) -> "Article":
        """Accepts a Group 2 clean article record, dict, or object."""
        if isinstance(raw, Mapping):
            g = lambda k, d=None: raw.get(k, d)  # noqa: E731
        else:
            g = lambda k, d=None: getattr(raw, k, d)  # noqa: E731

        url = g("url", "") or ""
        ticker = str(g("ticker", "") or "").strip().upper()
        title = str(g("title", "") or "").strip()
        if not ticker:
            raise ValueError("Group 2 article is missing required field 'ticker'")
        if not title:
            raise ValueError("Group 2 article is missing required field 'title'")
        aid = g("article_id")
        if not aid:
            if not url:
                raise ValueError("Group 2 article requires 'article_id' or 'url' to identify the record")
            aid = make_article_id(url, ticker)

        clean_txt = (g("clean_text", "") or "").strip()
        desc = (g("description", "") or "").strip()

        rel = g("relevance_score")
        if rel is None:
            rel = g("relevance")
        if rel is not None:
            try:
                rel = float(rel)
            except (ValueError, TypeError) as exc:
                raise ValueError(f"Invalid relevance_score: {rel!r}") from exc
            if not math.isfinite(rel) or not 0.0 <= rel <= 1.0:
                raise ValueError("relevance_score must be a finite number between 0 and 1")

        indep = parse_optional_bool(g("independent_source"))

        return cls(
            article_id=str(aid),
            ticker=ticker,
            company_name=g("company_name", "") or "",
            title=title,
            clean_text=clean_txt,
            description=desc,
            url=url,
            source=g("source", "") or "",
            source_type=g("source_type", "") or "",
            primary_source=parse_optional_bool(g("primary_source", False)) is True,
            independent_source=indep,
            independent_source_id=g("independent_source_id", g("source_origin_id")),
            relevance_score=rel,
            duplicate_cluster_id=g("duplicate_cluster_id"),
            published_at=parse_iso(g("published_at")),
            first_seen_at=parse_iso(g("first_seen_at")),
        )
    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["published_at"] = self.published_at.isoformat() if self.published_at else None
        d["first_seen_at"] = self.first_seen_at.isoformat() if self.first_seen_at else None
        d["relevance"] = self.relevance_score
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
    sentiment_model_name: Optional[str] = None

    # Importance and source metadata
    importance_score: Optional[float] = None
    relevance_score: Optional[float] = None
    source_quality: Optional[float] = None
    time_weight: Optional[float] = None
    final_event_weight: Optional[float] = None
    sentiment_contribution: Optional[float] = None
    source_quality_category: List[str] = field(default_factory=list)
    source_quality_breakdown: Dict[str, Any] = field(default_factory=dict)
    importance_breakdown: Dict[str, Optional[float]] = field(default_factory=dict)
    time_weight_breakdown: Dict[str, Any] = field(default_factory=dict)
    weight_missing_inputs: List[str] = field(default_factory=list)
    article_count: int = 0
    independent_source_count: int = 0
    publisher_count: int = 0
    primary_source_confirmed: bool = False

    @property
    def event_timestamp(self) -> Optional[datetime]:
        return self.first_article_at or self.last_article_at

    @property
    def headline(self) -> str:
        return self.title

    @property
    def primary_source_present(self) -> bool:
        return self.primary_source_confirmed

    def to_group4_record(self) -> Dict[str, Any]:
        """Output format matching Group 3 -> Group 4 Event Record shared interface."""
        return {
            "event_id": self.event_id,
            "ticker": self.ticker,
            "event_type": self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type),
            "event_timestamp": self.event_timestamp.isoformat() if self.event_timestamp else None,
            "headline": self.headline,
            "sentiment_score": self.sentiment_score,
            "sentiment_model_name": self.sentiment_model_name,
            "positive_probability": self.positive_probability,
            "neutral_probability": self.neutral_probability,
            "negative_probability": self.negative_probability,
            "importance_score": self.importance_score,
            "relevance_score": self.relevance_score,
            "source_quality": self.source_quality,
            "time_weight": self.time_weight,
            "final_event_weight": self.final_event_weight,
            "sentiment_contribution": self.sentiment_contribution,
            "source_quality_category": self.source_quality_category,
            "source_quality_breakdown": self.source_quality_breakdown,
            "importance_breakdown": self.importance_breakdown,
            "time_weight_breakdown": self.time_weight_breakdown,
            "weight_missing_inputs": self.weight_missing_inputs,
            "article_count": self.article_count,
            "publisher_count": self.publisher_count,
            "independent_source_count": self.independent_source_count,
            "primary_source_present": self.primary_source_present,
        }

    def to_dict(self) -> Dict[str, Any]:
        d = asdict(self)
        d["event_type"] = self.event_type.value if isinstance(self.event_type, EventType) else str(self.event_type)
        d["first_article_at"] = self.first_article_at.isoformat() if self.first_article_at else None
        d["last_article_at"] = self.last_article_at.isoformat() if self.last_article_at else None
        d["event_timestamp"] = d["first_article_at"]
        d["headline"] = self.title
        d["primary_source_present"] = self.primary_source_confirmed
        return d


def parse_optional_bool(value):
    """Parse explicit boolean metadata; preserve missing/invalid as unknown."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().casefold()
        if normalized in {"true", "1", "yes"}: return True
        if normalized in {"false", "0", "no"}: return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return None
