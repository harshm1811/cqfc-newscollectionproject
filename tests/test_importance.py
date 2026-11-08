import pytest

from models.importance import ImportanceConfig, score_event_importance


def test_importance_yaml_weights_are_valid_and_custom_weights_work():
    event = {"event_id": "e1", "event_type": "earnings", "primary_source_confirmed": True}
    default = score_event_importance(event)
    assert default["importance_score"] is not None
    custom = ImportanceConfig(factor_weights={
        "event_type": 0.5,
        "financial_magnitude": 0.0,
        "independent_source_count": 0.0,
        "primary_source_confirmation": 0.5,
        "company_specificity": 0.0,
        "novelty": 0.0,
        "quantitative_information": 0.0,
        "breaking_news_status": 0.0,
    })
    assert score_event_importance(event, config=custom)["importance_score"] == pytest.approx(0.9)
    invalid = ImportanceConfig(factor_weights={**custom.factor_weights, "novelty": 0.2})
    with pytest.raises(ValueError, match="sum to 1"):
        score_event_importance(event, config=invalid)
    negative = ImportanceConfig(factor_weights={**custom.factor_weights, "novelty": -0.1})
    with pytest.raises(ValueError, match="non-negative"):
        score_event_importance(event, config=negative)


def test_missing_importance_factors_are_reported_and_not_imputed():
    result = score_event_importance({"event_id": "e1"})
    assert result["importance_score"] is None
    assert len(result["missing_factors"]) == 8
    assert result["available_weight"] == 0
