"""Connect the Group 1 collection, Group 2 processing, Group 3 analysis,
and Group 4 SQLite persistence stages without changing their public contracts.

The default article processing path uses text supplied by feeds. Optional page
extraction can be enabled for a bounded number of URLs by the caller.
"""

from __future__ import annotations

import json
import math
import tempfile
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

import pandas as pd

from pipeline import collect_equity_news
from group2_pipeline import run_pipeline as run_group2_pipeline
from group3_pipeline import run_group3_pipeline

from .database.initialize import initialize_database
from .pipeline import (
    Group1Adapter,
    Group2Adapter,
    Group3Adapter,
    Group4Adapter,
    PipelineOrchestrator,
)
from .repository import Repository, RepositoryError
from .runs import RunTracker


class _IntegrationRunTracker(RunTracker):
    """Keep record counts and upstream partial failures in the Group 4 run row."""

    def __init__(self, db_path: str | Path | None):
        super().__init__(db_path)
        self.run_id: str | None = None
        self.article_count = 0
        self.event_count = 0
        self.integration_failures: list[dict[str, Any]] = []

    def start(self, **kwargs: Any) -> str:
        self.run_id = super().start(**kwargs)
        return self.run_id

    def finish(
        self,
        run_id: str,
        *,
        article_count: int = 0,
        event_count: int = 0,
        failures: list[Mapping[str, Any]] | None = None,
        status: str | None = None,
    ) -> None:
        all_failures = [dict(item) for item in (failures or [])]
        all_failures.extend(self.integration_failures)
        final_status = status
        if all_failures and final_status == "succeeded":
            final_status = "partial_failure"
        super().finish(
            run_id,
            article_count=self.article_count or article_count,
            event_count=self.event_count or event_count,
            failures=all_failures,
            status=final_status,
        )


def _upsert(repository: Repository, table: str, key: str, record: dict[str, Any]) -> dict[str, Any]:
    """Insert or update through the Group 4 repository API."""
    existing = repository.get(table, key, record[key])
    if existing is None:
        return repository.save(table, record)
    changes = {field: value for field, value in record.items() if field != key}
    for field, value in tuple(changes.items()):
        if field.endswith("_json") and value is not None and not isinstance(value, str):
            changes[field] = json.dumps(value, ensure_ascii=False, allow_nan=False)
    repository.update(table, key, record[key], changes)
    return {**existing, **record}


def _source_id(repository: Repository, source: str, source_type: str, primary: bool) -> int:
    """Resolve source identity without conflating primary and secondary records."""
    name = source.strip() or "Unknown"
    current = repository.get("SOURCES", "name", name)
    if current and (
        current.get("source_type") != source_type
        or bool(current.get("primary_source")) != bool(primary)
    ):
        qualifier = "primary" if primary else "secondary"
        name = f"{name} [{source_type or 'UNKNOWN'}; {qualifier}]"
        current = repository.get("SOURCES", "name", name)
    if current:
        return int(current["source_id"])
    saved = repository.save("SOURCES", {
        "name": name,
        "source_type": source_type or "UNKNOWN",
        "primary_source": int(bool(primary)),
    })
    return int(saved["source_id"])


def _clean_iso(value: Any) -> str | None:
    if value is None or value == "":
        return None
    if hasattr(value, "to_pydatetime"):
        value = value.to_pydatetime()
    if isinstance(value, datetime):
        dt = value
    else:
        try:
            dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _persist_outputs(
    repository: Repository,
    tracker: _IntegrationRunTracker,
    profile: Mapping[str, Any],
    processed_articles: list[dict[str, Any]],
    group3_result: Any,
) -> dict[str, int]:
    ticker = str(profile["ticker"]).upper()
    articles_saved = 0
    events_saved = 0
    features_saved = 0

    for article in processed_articles:
        source = str(article.get("source") or "Unknown")
        source_type = str(article.get("source_type") or "UNKNOWN")
        primary = article.get("primary_source") is True
        source_id = _source_id(repository, source, source_type, primary)
        record = {
            "article_id": str(article["article_id"]),
            "ticker": str(article.get("ticker") or ticker).upper(),
            "source_id": source_id,
            "title": article.get("title"),
            "description": article.get("description"),
            "url": article.get("url"),
            "published_at": _clean_iso(article.get("published_at")),
            "first_seen_at": _clean_iso(article.get("first_seen_at")),
            "retrieved_at": _clean_iso(article.get("retrieved_at")),
            "clean_text": article.get("clean_text"),
            "relevance_score": article.get("relevance_score"),
            "duplicate_cluster_id": article.get("duplicate_cluster_id"),
            "primary_source": int(article.get("primary_source") is True),
            "independent_source": (
                int(article["independent_source"]) if article.get("independent_source") is not None else None
            ),
            "independent_source_id": article.get("independent_source_id") or article.get("source_origin_id"),
        }
        _upsert(repository, "ARTICLES", "article_id", record)
        articles_saved += 1
        tracker.article_count = articles_saved

    for event in group3_result.event_records:
        probs = {
            "positive": event.get("positive_probability"),
            "neutral": event.get("neutral_probability"),
            "negative": event.get("negative_probability"),
        }
        record = {
            "event_id": str(event["event_id"]),
            "ticker": str(event.get("ticker") or ticker).upper(),
            "type": event.get("event_type"),
            "event_labels_json": event.get("event_labels", []),
            "event_type_confidence": event.get("event_type_confidence"),
            "event_type_scores_json": event.get("event_type_scores", {}),
            "timestamp": _clean_iso(event.get("event_timestamp")),
            "headline": event.get("headline"),
            "sentiment_score": event.get("sentiment_score"),
            "sentiment_probabilities_json": probs,
            "importance": event.get("importance_score"),
            "article_count": event.get("article_count", 0),
            "source_count": event.get("publisher_count", 0),
            "independent_source_count": event.get("independent_source_count"),
            "primary_source_present": int(bool(event.get("primary_source_present"))),
        }
        _upsert(repository, "EVENTS", "event_id", record)
        events_saved += 1
        tracker.event_count = events_saved

    for mapping in group3_result.mappings:
        repository.link_article_event(mapping.article_id, mapping.event_id)

    for article in group3_result.articles:
        sentiment = article.sentiment
        if sentiment is None:
            continue
        probabilities = {
            "positive": sentiment.positive_probability,
            "neutral": sentiment.neutral_probability,
            "negative": sentiment.negative_probability,
        }
        label = max(probabilities, key=lambda key: probabilities[key])
        existing = repository.list_records(
            "SENTIMENT_RESULTS", filters={"article_id": article.article_id}, limit=10000
        )
        match = next(
            (row for row in existing if row.get("model_version") == sentiment.model_name),
            None,
        )
        sentiment_record = {
            "article_id": article.article_id,
            "event_id": None,
            "model_version": sentiment.model_name or "unspecified",
            "label": label,
            "score": sentiment.sentiment_score,
            "probabilities_json": probabilities,
        }
        if match:
            sentiment_record["sentiment_id"] = match["sentiment_id"]
            _upsert(repository, "SENTIMENT_RESULTS", "sentiment_id", sentiment_record)
        else:
            repository.save("SENTIMENT_RESULTS", sentiment_record)

    frame = group3_result.daily_features
    if not frame.empty:
        metadata_columns = {"ticker", "date", "feature_date"}
        for row in frame.to_dict(orient="records"):
            feature_ticker = str(row.get("ticker") or ticker).upper()
            feature_date = row.get("feature_date", row.get("date"))
            if hasattr(feature_date, "strftime"):
                feature_date = feature_date.strftime("%Y-%m-%d")
            else:
                feature_date = str(feature_date)[:10]
            existing = repository.list_records(
                "DAILY_FEATURES",
                filters={"ticker": feature_ticker, "feature_date": feature_date},
                limit=10000,
            )
            by_name = {item["feature_name"]: item for item in existing}
            for name, value in row.items():
                if name in metadata_columns or value is None or pd.isna(value):
                    continue
                if hasattr(value, "item"):
                    value = value.item()
                if isinstance(value, bool):
                    value = int(value)
                if not isinstance(value, (int, float)) or not math.isfinite(float(value)):
                    continue
                record = {
                    "ticker": feature_ticker,
                    "feature_date": feature_date,
                    "feature_name": str(name),
                    "feature_value": float(value),
                    "source_run_id": tracker.run_id,
                }
                previous = by_name.get(str(name))
                if previous:
                    record["feature_id"] = previous["feature_id"]
                    _upsert(repository, "DAILY_FEATURES", "feature_id", record)
                else:
                    saved = repository.save("DAILY_FEATURES", record)
                    by_name[str(name)] = saved
                features_saved += 1

    return {
        "articles": articles_saved,
        "events": events_saved,
        "features": features_saved,
        "sentiments": sum(article.sentiment is not None for article in group3_result.articles),
    }


def run_equity_intelligence(
    query: str,
    *,
    start_date: str | None = None,
    end_date: str | None = None,
    config_path: str = "config/default_config.yaml",
    db_path: str | Path | None = None,
    fetch_article_text: bool = False,
    article_text_limit: int = 20,
    min_relevance_threshold: float | None = None,
    semantic_similarity_threshold: float = 0.65,
) -> dict[str, Any]:
    """Run Groups 1→2→3→4 and persist actual outputs through the Group 4 API.

    Synthetic test/demo fixtures are never read by this entry point.
    """
    if not query or not query.strip():
        raise ValueError("A company name or ticker is required")
    if article_text_limit < 0:
        raise ValueError("article_text_limit cannot be negative")
    if not 0 <= semantic_similarity_threshold <= 1:
        raise ValueError("semantic_similarity_threshold must be between 0 and 1")

    initialize_database(db_path)
    repository = Repository(db_path)
    tracker = _IntegrationRunTracker(db_path)
    state: dict[str, Any] = {}

    def group1(payload: Mapping[str, Any]) -> dict[str, Any]:
        result = collect_equity_news(
            str(payload["query"]),
            start_date=payload.get("start_date"),
            end_date=payload.get("end_date"),
            config_path=str(payload["config_path"]),
            run_id=tracker.run_id,
        )
        state["group1"] = result
        if tracker.run_id:
            run_row = repository.get("COLLECTION_RUNS", "run_id", tracker.run_id) or {}
            try:
                configuration = json.loads(run_row.get("configuration_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                configuration = {}
            configuration["generated_query_categories"] = result.get("query_categories", {})
            configuration["collector_statuses"] = {
                name: {key: value for key, value in outcome.items() if key != "errors"}
                for name, outcome in result.get("collector_results", {}).items()
            }
            repository.update(
                "COLLECTION_RUNS", "run_id", tracker.run_id,
                {
                    "collectors_json": json.dumps(list(result.get("collector_results", {}))),
                    "configuration_json": json.dumps(configuration, ensure_ascii=False),
                },
            )
        profile = result.get("equity_profile")
        if profile:
            ticker = str(profile["ticker"]).upper()
            current = repository.get("EQUITIES", "ticker", ticker)
            if current is None:
                repository.save("EQUITIES", {
                    "ticker": ticker,
                    "company_name": profile.get("company_name"),
                    "exchange": profile.get("exchange"),
                    "country": profile.get("country"),
                })
            elif any(current.get(key) != profile.get(key) for key in ("company_name", "exchange", "country")):
                repository.update(
                    "EQUITIES", "ticker", ticker,
                    {key: profile.get(key) for key in ("company_name", "exchange", "country")},
                )
            repository.update(
                "COLLECTION_RUNS", "run_id", str(tracker.run_id),
                {"requested_ticker": ticker},
            )
        for collector, outcome in result.get("collector_results", {}).items():
            for error in outcome.get("errors", []):
                tracker.integration_failures.append({"stage": "Group 1", **error})
            if outcome.get("unsupported_reason"):
                tracker.integration_failures.append({
                    "stage": "Group 1", "collector": collector,
                    "error": outcome["unsupported_reason"],
                })
        if result.get("collection_status") in {"failed", "unsupported"}:
            details = result.get("message") or result.get("errors") or result.get("collection_status")
            raise RuntimeError(f"Group 1 collection {result.get('collection_status')}: {details}")
        return {"group1": result}

    def group2(payload: Mapping[str, Any]) -> dict[str, Any]:
        raw_articles = payload["group1"].get("raw_articles", [])
        extraction_status_counts: dict[str, int] = {}
        if fetch_article_text and raw_articles:
            from extraction.article_extractor import ArticleExtractor

            extractor = ArticleExtractor()
            enriched = []
            for index, item in enumerate(raw_articles):
                record = dict(item)
                if index < article_text_limit:
                    extracted = extractor.extract_from_record(record, fetch_network=True)
                    status_name = extracted.status.value
                    extraction_status_counts[status_name] = extraction_status_counts.get(status_name, 0) + 1
                    if extracted.article_text:
                        record["content"] = extracted.article_text
                    if not record.get("description") and extracted.description:
                        record["description"] = extracted.description
                    if not record.get("title") and extracted.title:
                        record["title"] = extracted.title
                    if not record.get("published_at") and extracted.published_at:
                        record["published_at"] = extracted.published_at
                    if extracted.status.value in {"FAILED", "BLOCKED", "PAYWALLED"}:
                        tracker.integration_failures.append({
                            "stage": "Group 2 extraction",
                            "status": extracted.status.value,
                            "url": record.get("url"),
                            "error": extracted.error_message or f"Article extraction status: {extracted.status.value}",
                        })
                enriched.append(record)
            raw_articles = enriched
        with tempfile.TemporaryDirectory(prefix="equity-intelligence-") as folder:
            input_path = Path(folder) / "raw_candidates.json"
            output_path = Path(folder) / "processed_articles.json"
            input_path.write_text(
                json.dumps(raw_articles, ensure_ascii=False, allow_nan=False),
                encoding="utf-8",
            )
            processed = run_group2_pipeline(
                input_path,
                output_path,
                min_relevance_threshold=min_relevance_threshold,
                semantic_similarity_threshold=semantic_similarity_threshold,
            )
        state["group2"] = processed
        state["extraction_status_counts"] = extraction_status_counts
        if tracker.run_id:
            run_row = repository.get("COLLECTION_RUNS", "run_id", tracker.run_id) or {}
            try:
                configuration = json.loads(run_row.get("configuration_json") or "{}")
            except (TypeError, json.JSONDecodeError):
                configuration = {}
            configuration["extraction_status_counts"] = extraction_status_counts
            configuration["group2_embedding_backend"] = processed.get("embedding_backend")
            configuration["semantic_similarity_threshold"] = semantic_similarity_threshold
            repository.update(
                "COLLECTION_RUNS", "run_id", tracker.run_id,
                {"configuration_json": json.dumps(configuration, ensure_ascii=False)},
            )
        return {**payload, "group2": processed}

    def group3(payload: Mapping[str, Any]) -> dict[str, Any]:
        result = run_group3_pipeline(payload["group2"].get("articles", []))
        state["group3"] = result
        model_name = result.sentiment_model_name
        fallback_reason = result.sentiment_fallback_reason
        if fallback_reason:
            tracker.integration_failures.append({
                "stage": "Group 3 sentiment",
                "model": model_name,
                "error": fallback_reason,
            })
        if tracker.run_id:
            repository.update(
                "COLLECTION_RUNS", "run_id", tracker.run_id,
                {"model_versions_json": json.dumps({
                    "sentiment": model_name,
                    "fallback_reason": fallback_reason,
                    "group2_embedding": (state.get("group2") or {}).get("embedding_backend"),
                }, ensure_ascii=False)},
            )
        return {**payload, "group3": result}

    def group4(payload: Mapping[str, Any]) -> dict[str, Any]:
        profile = payload["group1"].get("equity_profile")
        if not profile:
            raise RepositoryError("Group 4 cannot persist output without a resolved equity profile")
        counts = _persist_outputs(
            repository,
            tracker,
            profile,
            payload["group2"].get("articles", []),
            payload["group3"],
        )
        return {
            "ticker": profile["ticker"],
            "collection_status": payload["group1"].get("collection_status"),
            "counts": counts,
        }

    orchestration = PipelineOrchestrator(
        [
            Group1Adapter(group1),
            Group2Adapter(group2),
            Group3Adapter(group3),
            Group4Adapter(group4),
        ],
        tracker=tracker,
        repository=repository,
    )
    result = orchestration.run(
        {
            "query": query.strip(),
            "start_date": start_date,
            "end_date": end_date,
            "config_path": config_path,
        },
        start_time=start_date,
        end_time=end_date,
        configuration={
            "query": query.strip(),
            "config_path": config_path,
            "fetch_article_text": fetch_article_text,
            "article_text_limit": article_text_limit,
            "min_relevance_threshold": min_relevance_threshold,
            "semantic_similarity_threshold": semantic_similarity_threshold,
        },
    )
    run_row = tracker.get(result.run_id)
    group1_result = state.get("group1", {})
    group2_result = state.get("group2", {})
    group3_result = state.get("group3")
    counts = result.payload.get("counts", {}) if isinstance(result.payload, dict) else {}
    return {
        "run_id": result.run_id,
        "status": run_row.get("status") if run_row else result.status,
        "ticker": (group1_result.get("equity_profile") or {}).get("ticker"),
        "collection_status": group1_result.get("collection_status"),
        "raw_article_count": group1_result.get("total_articles", 0),
        "processed_article_count": counts.get("articles", len(group2_result.get("articles", []))),
        "event_count": counts.get("events", len(getattr(group3_result, "event_records", []))),
        "daily_feature_value_count": counts.get("features", 0),
        "sentiment_count": counts.get("sentiments", 0),
        "sentiment_model": getattr(group3_result, "sentiment_model_name", None),
        "sentiment_fallback_reason": getattr(group3_result, "sentiment_fallback_reason", None),
        "extraction_status_counts": state.get("extraction_status_counts", {}),
        "semantic_embedding_backend": (group2_result or {}).get("embedding_backend"),
        "failed_stages": [
            {"stage": stage.stage, "status": stage.status, "error": stage.error}
            for stage in result.stages if stage.status != "succeeded"
        ],
        "failures": json.loads(run_row["failures_json"] or "[]") if run_row else [],
    }


def main() -> None:
    import argparse

    parser = argparse.ArgumentParser(description="Collect, process, analyze, and store equity intelligence.")
    parser.add_argument("query", help="Company name, ticker, or supported alias")
    parser.add_argument("--start-date", help="Inclusive ISO-8601 start date/time")
    parser.add_argument("--end-date", help="Inclusive ISO-8601 end date/time")
    parser.add_argument("--config", default="config/default_config.yaml")
    parser.add_argument("--fetch-article-text", action="store_true")
    parser.add_argument("--article-text-limit", type=int, default=20)
    parser.add_argument("--min-relevance", type=float)
    parser.add_argument("--semantic-similarity-threshold", type=float, default=0.65)
    args = parser.parse_args()
    result = run_equity_intelligence(
        args.query,
        start_date=args.start_date,
        end_date=args.end_date,
        config_path=args.config,
        fetch_article_text=args.fetch_article_text,
        article_text_limit=args.article_text_limit,
        min_relevance_threshold=args.min_relevance,
        semantic_similarity_threshold=args.semantic_similarity_threshold,
    )
    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
