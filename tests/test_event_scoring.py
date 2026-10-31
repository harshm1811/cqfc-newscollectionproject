import pandas as pd
import pytest

from aggregation.adapters.input_adapter import adapt_enriched_outputs
from aggregation.event_scoring import calculate_event_scores
from aggregation.sentiment_index import event_contributions


def test_adapter_none_importance_is_later_filled_as_one_by_person3_logic():
    _, events, _ = adapt_enriched_outputs(
        [],
        [{"event_id": "e1", "ticker": "ABC", "first_article_at": "2026-01-01T00:00Z", "sentiment_score": 0.2}],
        [],
        event_scores={"e1": {"importance_score": None, "source_quality": 0.8, "time_weight": 0.9}},
    )
    assert pd.isna(events.loc[0, "importance_score"])
    contributions = event_contributions(events)
    assert contributions.loc[0, "importance_score"] == 1.0


def test_event_scores_have_exact_adapter_keys():
    event = {
        "event_id": "e1",
        "ticker": "ABC",
        "first_article_at": "2026-01-01T00:00:00Z",
        "event_type": "earnings",
        "primary_source_confirmed": True,
        "financial_magnitude": 0.7,
        "company_specificity": 0.8,
        "novelty": 0.6,
        "quantitative_information": 0.9,
        "breaking_news_status": False,
        "independent_source_count": 2,
    }
    result = calculate_event_scores(
        [event],
        [{"article_id": "a1", "source": "Exchange", "source_type": "exchange"}],
        article_event_ids={"a1": "e1"},
        as_of="2026-01-02T00:00:00Z",
    )
    assert set(result["e1"]) == {"importance_score", "source_quality", "time_weight"}
    assert all(0 <= result["e1"][key] <= 1 for key in result["e1"])


def test_event_scoring_rejects_event_with_no_importance_inputs():
    with pytest.raises(ValueError, match="all importance factors are missing"):
        calculate_event_scores(
            [{"event_id": "e-empty", "first_article_at": "2026-01-01T00:00:00Z"}],
            [],
            as_of="2026-01-02T00:00:00Z",
        )
