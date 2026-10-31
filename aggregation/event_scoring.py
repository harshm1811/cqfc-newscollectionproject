"""Calculate and package event-level importance, source, and time scores."""

from collections.abc import Mapping

from models._records import as_record
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
    """Build ``{event_id: {importance_score, source_quality, time_weight}}``.

    Article association uses Event.article_ids and/or an explicit
    article-to-event map. Diagnostics remain available from the individual
    scoring functions; this mapping contains exactly the adapter's three keys.
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
        quality = aggregate_event_source_quality(event, selected_articles, config=source_quality_config)
        decay = calculate_time_weight(event, as_of=as_of, config=time_decay_config)
        output[event_id] = {
            "importance_score": importance["importance_score"],
            "source_quality": quality["source_quality"],
            "time_weight": decay["time_weight"],
        }
    return output
