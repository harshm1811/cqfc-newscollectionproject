import pytest
from events.event_model import EventType

from models.importance import ImportanceConfig, score_event_importance


def test_importance_yaml_weights_are_valid_and_custom_weights_work():
    event = {"event_id": "e1", "event_type": "FinancialReport", "primary_source_confirmed": True}
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
    assert score_event_importance(event, config=custom)["importance_score"] == pytest.approx(0.925)
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


def test_event_type_materiality_uses_confidence_weighted_maximum():
    event = {
        "event_type": "Deal",
        "event_labels": ["Deal", "Dividend"],
        "type_scores": {"Deal": 0.8, "Dividend": 0.9},
    }
    result = score_event_importance(event)
    assert result["importance_components"]["event_type"] == pytest.approx(max(0.8 * 0.75, 0.9 * 0.65))


def test_other_event_uses_configured_weight_without_fabricated_confidence():
    result = score_event_importance({"event_type": "OTHER", "event_labels": ["OTHER"], "type_scores": {}})
    assert result["importance_components"]["event_type"] == pytest.approx(0.4)


@pytest.mark.parametrize("event_type", list(EventType))
def test_all_official_event_types_have_scores_and_enum_matches_string(event_type):
    enum_result = score_event_importance({"event_type": event_type})
    string_result = score_event_importance({"event_type": event_type.value.lower()})
    assert enum_result["importance_components"]["event_type"] is not None
    assert enum_result["importance_score"] == pytest.approx(string_result["importance_score"])


def test_importance_config_has_all_19_fin_deberta_labels():
    import yaml
    from pathlib import Path
    labels = yaml.safe_load(Path("config/importance.yaml").read_text(encoding="utf-8"))["event_type_scores"]
    assert len(labels) == 19
    assert labels["CSR/Brand"] == pytest.approx(0.45)
