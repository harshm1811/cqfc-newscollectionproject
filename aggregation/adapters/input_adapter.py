"""Convert Person 1 dataclasses or dictionaries into stable record tables.

Person 2 values are injected here, with visibly marked mock defaults. No
upstream models are redefined and identifiers/mappings are retained verbatim.
"""

from dataclasses import dataclass, field
from typing import Any, Mapping

import pandas as pd


def _dict(record: Any) -> dict:
    if isinstance(record, Mapping):
        return dict(record)
    method = getattr(record, "to_dict", None)
    if callable(method):
        return dict(method())
    raise TypeError(f"Expected a mapping or object with to_dict(), got {type(record)!r}")


def _sentiment(row: dict) -> dict:
    value = row.get("sentiment")
    if value is None:
        return row
    if isinstance(value, Mapping):
        return {**row, **value}
    method = getattr(value, "to_dict", None)
    if callable(method):
        sentiment = dict(method())
    elif hasattr(value, "__dict__"):
        sentiment = vars(value)
    else:
        sentiment = {}
    return {**row, **sentiment}


@dataclass
class InputAdapterConfig:
    mock_importance: float = 0.5
    mock_source_quality: float = 0.75
    mock_time_weight: float = 1.0
    mock_relevance: float = 1.0
    mock_fields: tuple[str, ...] = field(default=("importance_score", "source_quality", "time_weight"))


def adapt_enriched_outputs(articles, events, mappings, *, event_scores=None,
                           relevance_by_article=None, config=None):
    """Return normalized ``(articles_df, events_df, mappings_df)``.

    Timestamps are UTC-aware. Person 2 event fields take precedence over mock
    values. Event sentiment is used for event calculations, article sentiment
    remains available for source-agreement calculations.
    """
    config = config or InputAdapterConfig()
    event_scores = event_scores or {}
    relevance_by_article = relevance_by_article or {}
    article_rows = [_sentiment(_dict(x)) for x in articles]
    event_rows = [_dict(x) for x in events]
    mapping_rows = [_dict(x) for x in mappings]
    adf = pd.DataFrame(article_rows)
    edf = pd.DataFrame(event_rows)
    mdf = pd.DataFrame(mapping_rows, columns=list(dict.fromkeys([*(pd.DataFrame(mapping_rows).columns), "article_id", "event_id"])))
    for col in ("published_at", "first_seen_at"):
        if col in adf:
            adf[col] = pd.to_datetime(adf[col], utc=True, errors="coerce")
    for col in ("first_article_at", "last_article_at"):
        if col in edf:
            edf[col] = pd.to_datetime(edf[col], utc=True, errors="coerce")
    if not adf.empty:
        adf["relevance"] = adf.apply(lambda r: relevance_by_article.get(r.get("article_id"), r.get("relevance", config.mock_relevance)), axis=1)
    for field, default in (("importance_score", config.mock_importance), ("source_quality", config.mock_source_quality), ("time_weight", config.mock_time_weight)):
        if field not in edf:
            edf[field] = default
        if not edf.empty:
            edf[field] = edf.apply(lambda r: event_scores.get(r.get("event_id"), {}).get(field, r.get(field) if pd.notna(r.get(field)) else default), axis=1)
    # Relevance is article/equity scoped upstream. Reduce mapped article
    # relevance to an event-level mean for the event contribution formula.
    if not edf.empty and not adf.empty and not mdf.empty and "relevance" in adf:
        rel = mdf.merge(adf[["article_id", "relevance"]], on="article_id", how="left").groupby("event_id", as_index=False).relevance.mean()
        edf = edf.merge(rel, on="event_id", how="left", suffixes=("", "_mapped"))
        if "relevance_mapped" in edf:
            edf["relevance"] = edf["relevance_mapped"].fillna(edf.get("relevance", config.mock_relevance))
            edf = edf.drop(columns="relevance_mapped")
    elif not edf.empty and "relevance" not in edf:
        edf["relevance"] = config.mock_relevance
    if not edf.empty:
        edf["has_mock_scores"] = edf.apply(lambda r: any(r.get(k) == d for k, d in (("importance_score", config.mock_importance), ("source_quality", config.mock_source_quality), ("time_weight", config.mock_time_weight)) if k not in event_scores.get(r.get("event_id"), {})), axis=1)
    return adf, edf, mdf
