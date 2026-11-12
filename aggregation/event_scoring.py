"""Calculate and package event-level importance, source, and time scores."""

from collections.abc import Mapping

from models._records import as_record, get_value
from models.importance import score_event_importance
from models.source_quality import aggregate_event_source_quality
from .time_decay import calculate_time_weight


def calculate_event_scores(
    events,
    articles,
    *,
    article_event_ids: Mapping | None = None,
    importance_factors_by_event: Mapping | None = None,
    as_of=None,
    importance_config=None,
    source_quality_config=None,
    time_decay_config=None,
):
    """Build event-level scoring values and diagnostics used by feature aggregation.

    Article association uses Event.article_ids and/or an explicit
    article-to-event map. Missing relevance remains explicit and gives the event
    zero feature weight while retaining its diagnostic components.
    """
    article_event_ids = article_event_ids or {}
    importance_factors_by_event = importance_factors_by_event or {}
    article_rows = [(as_record(article), article) for article in articles]
    output = {}
    for event in events:
        row = as_record(event)
        event_id = row.get("event_id")
        article_ids = set(row.get("article_ids") or [])
        selected_articles = [
            article for article_row, article in article_rows
            if article_row.get("article_id") in article_ids
            or article_event_ids.get(article_row.get("article_id")) == event_id
        ]
        relevance_values = []
        for article in selected_articles:
            value = get_value(article, "relevance_score", "relevance")
            try:
                value = float(value)
            except (TypeError, ValueError):
                continue
            if 0.0 <= value <= 1.0:
                relevance_values.append(value)
        relevance = sum(relevance_values) / len(relevance_values) if relevance_values else None
        importance = score_event_importance(
            event,
            config=importance_config,
            additional_factors=importance_factors_by_event.get(event_id),
        )
        if importance["importance_score"] is None:
            raise ValueError(
                f"Cannot calculate event scores for {event_id!r}: "
                "all importance factors are missing. Supply at least one scored factor."
            )
        if not selected_articles:
            raise ValueError(f"Cannot calculate source quality for {event_id!r}: no associated articles were found.")
        quality = aggregate_event_source_quality(event, selected_articles, config=source_quality_config)
        decay = calculate_time_weight(event, as_of=as_of, config=time_decay_config)
        sentiment = get_value(event, "sentiment_score")
        missing_weight_inputs = [
            name for name, value in (
                ("relevance_score", relevance),
                ("importance_score", importance["importance_score"]),
                ("source_quality", quality["source_quality"]),
                ("time_weight", decay["time_weight"]),
            ) if value is None
        ]
        final_weight = 0.0
        if not missing_weight_inputs:
            final_weight = min(1.0, max(0.0, relevance * importance["importance_score"] * quality["source_quality"] * decay["time_weight"]))
        output[event_id] = {
            "relevance_score": relevance,
            "importance_score": importance["importance_score"],
            "source_quality": quality["source_quality"],
            "time_weight": decay["time_weight"],
            "final_event_weight": final_weight,
            "sentiment_contribution": float(sentiment) * final_weight if sentiment is not None else None,
            "source_quality_category": quality["source_category"],
            "source_quality_breakdown": quality["source_quality_components"],
            "importance_breakdown": importance["importance_components"],
            "time_weight_breakdown": decay,
            "weight_missing_inputs": missing_weight_inputs,
        }
    return output
