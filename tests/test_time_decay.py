from datetime import datetime, timezone
from math import exp, isclose, log

import pytest

from aggregation.time_decay import TimeDecayConfig, calculate_time_weight


def test_decay_config_is_loaded_from_yaml():
    config = TimeDecayConfig.from_yaml()
    assert config.half_life_hours == 24.0
    assert config.timestamp_fields == ("first_article_at", "published_at", "first_seen_at")
    assert config.missing_timestamp_weight == 1.0
    assert TimeDecayConfig().half_life_hours == config.half_life_hours


def test_half_life_matches_exponential_decay_in_hours():
    now = datetime(2026, 1, 2, tzinfo=timezone.utc)
    result = calculate_time_weight(
        {"first_article_at": "2026-01-01T00:00:00Z"},
        as_of=now,
        config=TimeDecayConfig(half_life_hours=24),
    )
    expected_lambda = log(2) / 24
    assert result["event_age_hours"] == 24
    assert result["lambda_used"] == pytest.approx(expected_lambda)
    assert result["time_weight"] == pytest.approx(0.5)
    assert isclose(result["time_weight"], exp(-expected_lambda * 24))


@pytest.mark.parametrize(
    "timestamp, expected_age",
    [
        ("2026-01-01T00:00:00-05:00", 5.0),
        ("not-a-timestamp", None),
        (None, None),
        ("1970-01-01T00:00:00Z", None),
    ],
)
def test_timestamp_timezone_invalid_missing_and_epoch_fallback(timestamp, expected_age):
    result = calculate_time_weight(
        {"first_article_at": timestamp},
        as_of="2026-01-01T10:00:00Z",
        config=TimeDecayConfig(half_life_hours=24, missing_timestamp_weight=0.25),
    )
    assert result["event_age_hours"] == expected_age
    if expected_age is None:
        assert result["time_weight"] == 0.25
    else:
        expected_weight = exp(-(log(2) / 24) * expected_age)
        assert result["time_weight"] == pytest.approx(expected_weight)


def test_time_decay_config_rejects_invalid_half_life():
    with pytest.raises(ValueError):
        TimeDecayConfig(half_life_hours=float("nan"))
