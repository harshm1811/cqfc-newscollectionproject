import pandas as pd
import pytest

from aggregation.adapters.input_adapter import adapt_enriched_outputs
from aggregation.event_scoring import calculate_event_scores
from aggregation.sentiment_index import event_contributions


def test_adapter_none_importance_is_excluded_from_weighted_contribution():
    _, events, _ = adapt_enriched_outputs(
        [],
        [{"event_id": "e1", "ticker": "ABC", "first_article_at": "2026-01-01T00:00Z", "sentiment_score": 0.2}],
        [],
        event_scores={"e1": {"importance_score": None, "source_quality": 0.8, "time_weight": 0.9}},
    )
    assert pd.isna(events.loc[0, "importance_score"])
    contributions = event_contributions(events)
    assert pd.isna(contributions.loc[0, "importance_score"])
    assert contributions.loc[0, "weight"] == 0.0
    assert contributions.loc[0, "score_missing_reason"] == "importance_score"


def test_event_scores_include_adapter_values_and_diagnostics():
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
    assert {"importance_score", "source_quality", "time_weight", "relevance_score", "final_event_weight", "sentiment_contribution", "source_quality_category", "source_quality_breakdown"}.issubset(result["e1"])
    assert all(0 <= result["e1"][key] <= 1 for key in ("importance_score", "source_quality", "time_weight", "final_event_weight"))
    assert result["e1"]["relevance_score"] is None
    assert result["e1"]["final_event_weight"] == 0.0
    assert result["e1"]["weight_missing_inputs"] == ["relevance_score"]


def test_event_weight_multiplies_relevance_importance_quality_and_decay():
    event = {
        "event_id": "weighted", "ticker": "ABC", "event_type": "earnings",
        "first_article_at": "2026-01-02T00:00:00Z", "sentiment_score": 0.5,
        "primary_source_confirmed": False, "financial_magnitude": 0.8,
        "company_specificity": 0.8, "novelty": 0.8,
        "quantitative_information": 0.8, "breaking_news_status": False,
        "independent_source_count": 0,
    }
    result = calculate_event_scores(
        [event],
        [{"article_id": "a", "source": "Reuters", "source_type": "NEWS_RSS", "relevance_score": 0.6}],
        article_event_ids={"a": "weighted"}, as_of="2026-01-02T00:00:00Z",
    )["weighted"]
    expected = result["relevance_score"] * result["importance_score"] * result["source_quality"] * result["time_weight"]
    assert result["final_event_weight"] == pytest.approx(expected)
    assert result["sentiment_contribution"] == pytest.approx(0.5 * expected)
    assert result["source_quality"] == 0.86


def test_event_scoring_rejects_event_with_no_importance_inputs():
    with pytest.raises(ValueError, match="all importance factors are missing"):
        calculate_event_scores(
            [{"event_id": "e-empty", "first_article_at": "2026-01-01T00:00:00Z"}],
            [],
            as_of="2026-01-02T00:00:00Z",
        )
