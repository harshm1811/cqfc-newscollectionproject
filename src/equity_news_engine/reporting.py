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
    """Build a structured report from stored articles, events and daily features."""
    filters = {"ticker": ticker} if ticker else {}
    articles = repository.list_records("ARTICLES", filters=filters, start=start, end=end, limit=10000)
    events = repository.list_records("EVENTS", filters=filters, start=start, end=end, limit=10000)
    features = repository.list_records("DAILY_FEATURES", filters=filters, start=start, end=end, limit=10000)
    sentiments = repository.sentiment_records(ticker=ticker, start=start, end=end)
    equities = repository.list_records(
        "EQUITIES", filters={"ticker": ticker} if ticker else {}, limit=10000
    )
    equity_by_ticker = {row["ticker"]: row for row in equities}
    sources = repository.list_records("SOURCES", limit=10000)
    runs = repository.list_records(
        "COLLECTION_RUNS",
        filters={"requested_ticker": ticker} if ticker else {},
        start=start, end=end, order_by="created_at", limit=1000,
    )

    by_day: dict[tuple[str, str], dict[str, Any]] = {}
    for row in features:
        key = (row["ticker"], row["feature_date"])
        by_day.setdefault(key, {"date": row["feature_date"], "ticker": row["ticker"]})[row["feature_name"]] = row["feature_value"]
    daily_series = [by_day[key] for key in sorted(by_day)]
    latest = daily_series[-1] if daily_series else {}
    latest_by_ticker: dict[str, dict[str, Any]] = {}
    for row in daily_series:
        latest_by_ticker[row["ticker"]] = row
    weighted_values = [
        (float(row["weighted_sentiment"]), max(1, int(row.get("relevant_article_count") or row.get("news_count") or 1)))
        for row in daily_series if row.get("weighted_sentiment") is not None
    ]
    total_weight = sum(weight for _, weight in weighted_values)
    overall_weighted = (
        sum(value * weight for value, weight in weighted_values) / total_weight
        if total_weight else None
    )
    source_by_id = {row.get("source_id"): row for row in sources}
    source_counts: dict[Any, int] = {}
    for article in articles:
        source_id = article.get("source_id")
        source_counts[source_id] = source_counts.get(source_id, 0) + 1
    source_analysis = [
        {
            "source": (source_by_id.get(source_id) or {}).get("name", "Unknown"),
            "source_type": (source_by_id.get(source_id) or {}).get("source_type", "UNKNOWN"),
            "primary_source": bool((source_by_id.get(source_id) or {}).get("primary_source")),
            "article_count": count,
        }
        for source_id, count in sorted(source_counts.items(), key=lambda item: item[1], reverse=True)
    ]
    scoped_sources = [source_by_id[key] for key in source_counts if key in source_by_id]
    event_type_counts: dict[str, int] = {}
    for event in events:
        kind = str(event.get("type") or "OTHER")
        event_type_counts[kind] = event_type_counts.get(kind, 0) + 1
    positives = sorted(
        (row for row in events if (row.get("sentiment_score") or 0) > 0),
        key=lambda row: (row.get("importance") or 0, row.get("sentiment_score") or 0), reverse=True,
    )
    negatives = sorted(
        (row for row in events if (row.get("sentiment_score") or 0) < 0),
        key=lambda row: (-(row.get("importance") or 0), row.get("sentiment_score") or 0),
    )
    failures = []
    for run in runs:
        try:
            run_failures = json.loads(run.get("failures_json") or "[]")
        except (TypeError, json.JSONDecodeError):
            run_failures = [{"stage": "run_tracking", "error": "Stored failure details are invalid JSON"}]
        failures.extend({"run_id": run["run_id"], **failure} for failure in run_failures)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scope": {"ticker": ticker, "start": start, "end": end},
        "equity": equity_by_ticker.get(ticker) if ticker else [
            equity_by_ticker[key] for key in sorted(equity_by_ticker)
        ],
        "record_counts": {"articles": len(articles), "events": len(events), "features": len(features), "sentiment_results": len(sentiments), "sources": len(scoped_sources)},
        "coverage": {
            "relevant_articles": sum(float(row.get("relevance_score") or 0) > 0 for row in articles),
            "unique_event_count": len(events),
            "publisher_count": len(source_counts),
        },
        "sentiment": {
            "overall_weighted_sentiment": overall_weighted if ticker else None,
            "latest_feature_date": latest.get("date") if ticker else None,
            "latest_24h": latest.get("sentiment_1d") if ticker else None,
            "latest_7d": latest.get("sentiment_7d") if ticker else None,
            "latest_30d": latest.get("sentiment_30d") if ticker else None,
            "latest_by_ticker": list(latest_by_ticker.values()),
            "daily_trend": daily_series,
        },
        "event_breakdown": dict(sorted(event_type_counts.items())),
        "major_positive_events": positives[:10],
        "major_negative_events": negatives[:10],
        "emerging_themes": [
            {"event_type": kind, "event_count": count}
            for kind, count in sorted(event_type_counts.items(), key=lambda item: item[1], reverse=True)[:10]
        ],
        "key_risks": [
            {"event_id": row.get("event_id"), "event_type": row.get("type"),
             "headline": row.get("headline"), "sentiment_score": row.get("sentiment_score"),
             "importance": row.get("importance")}
            for row in negatives[:10]
        ],
        "source_analysis": source_analysis,
        "analysis_runs": runs,
        "failures": failures,
        "articles": articles, "events": events, "daily_features": features,
        "sentiment_results": sentiments, "sources": scoped_sources,
        "data_status": "empty" if not any((articles, events, features, sentiments)) else "available",
    }


def feature_frame(records: list[dict[str, Any]]) -> pd.DataFrame:
    """Pivot stored daily feature rows into one ticker/date series for display."""
    if not records:
        return pd.DataFrame()
    frame = pd.DataFrame.from_records(records)
    required = {"ticker", "feature_date", "feature_name", "feature_value"}
    if not required.issubset(frame.columns):
        return pd.DataFrame()
    return (
        frame.pivot_table(index=["ticker", "feature_date"], columns="feature_name",
                          values="feature_value", aggfunc="last")
        .reset_index()
        .sort_values(["ticker", "feature_date"])
    )


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
