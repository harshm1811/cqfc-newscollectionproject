"""Database-backed intelligence reports, tabular exports, and chart builders."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

import pandas as pd
import plotly.express as px

from .repository import Repository


EXPORT_TABLES = {"articles": "ARTICLES", "events": "EVENTS", "features": "DAILY_FEATURES"}


def records_for_export(repository: Repository, dataset: str, *, ticker: str | None = None,
                       start: str | None = None, end: str | None = None) -> list[dict[str, Any]]:
    """Retrieve an allowlisted export dataset using repository methods."""
    if dataset not in EXPORT_TABLES:
        raise ValueError(f"Unsupported export dataset: {dataset}")
    table = EXPORT_TABLES[dataset]
    filters = {"ticker": ticker} if ticker and table != "EVENTS" else {}
    if ticker and table == "EVENTS":
        filters = {"ticker": ticker}
    return repository.list_records(table, filters=filters, start=start, end=end, limit=10000)


def export_csv(records: list[dict[str, Any]]) -> str:
    """Serialize actual records to CSV; an empty dataset returns an empty string."""
    return pd.DataFrame.from_records(records).to_csv(index=False)


def export_json(records: list[dict[str, Any]]) -> str:
    """Serialize actual records to UTF-8 friendly JSON."""
    return json.dumps(records, ensure_ascii=False, indent=2, default=str)


def build_intelligence_report(repository: Repository, *, ticker: str | None = None,
                              start: str | None = None, end: str | None = None) -> dict[str, Any]:
    """Build a transparent structured summary of records currently in the database."""
    filters = {"ticker": ticker} if ticker else {}
    articles = repository.list_records("ARTICLES", filters=filters, start=start, end=end, limit=10000)
    events = repository.list_records("EVENTS", filters=filters, start=start, end=end, limit=10000)
    features = repository.list_records("DAILY_FEATURES", filters=filters, start=start, end=end, limit=10000)
    sentiments = repository.sentiment_records(ticker=ticker, start=start, end=end)
    sources = repository.list_records("SOURCES", limit=10000)
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"ticker": ticker, "start": start, "end": end},
        "record_counts": {"articles": len(articles), "events": len(events), "features": len(features), "sentiment_results": len(sentiments), "sources": len(sources)},
        "articles": articles, "events": events, "daily_features": features,
        "sentiment_results": sentiments, "sources": sources,
        "data_status": "empty" if not any((articles, events, features, sentiments)) else "available",
    }


def news_volume_chart(records: list[dict[str, Any]]):
    frame = pd.DataFrame(records)
    if frame.empty or "published_at" not in frame:
        return None
    frame["date"] = pd.to_datetime(frame["published_at"], errors="coerce", utc=True).dt.date
    frame = frame.dropna(subset=["date"])
    if frame.empty:
        return None
    counts = frame.groupby("date").size().rename("Articles").reset_index()
    return px.bar(counts, x="date", y="Articles", title="News volume")


def sentiment_chart(records: list[dict[str, Any]]):
    frame = pd.DataFrame(records)
    if frame.empty or "label" not in frame:
        return None
    counts = frame["label"].fillna("Unlabeled").value_counts().rename_axis("Sentiment").reset_index(name="Results")
    return px.bar(counts, x="Sentiment", y="Results", title="Sentiment results")


def event_importance_chart(records: list[dict[str, Any]]):
    frame = pd.DataFrame(records)
    if frame.empty or "importance" not in frame:
        return None
    frame = frame.dropna(subset=["importance"])
    if frame.empty:
        return None
    return px.histogram(frame, x="importance", nbins=10, title="Event importance")


def event_type_chart(records: list[dict[str, Any]]):
    frame = pd.DataFrame(records)
    if frame.empty or "type" not in frame:
        return None
    counts = frame["type"].fillna("Unspecified").value_counts().rename_axis("Event type").reset_index(name="Events")
    return px.bar(counts, x="Event type", y="Events", title="Events by type")
