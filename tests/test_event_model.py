from datetime import datetime, timedelta, timezone

import pytest

from events.event_model import Article, parse_iso


@pytest.mark.parametrize("value, expected", [
    ("2026-11-12T10:30:00Z", datetime(2026, 11, 12, 10, 30, tzinfo=timezone.utc)),
    ("2026-11-12T15:30:00+05:00", datetime(2026, 11, 12, 10, 30, tzinfo=timezone.utc)),
    (datetime(2026, 11, 12, 10, 30, tzinfo=timezone(timedelta(hours=2))), datetime(2026, 11, 12, 8, 30, tzinfo=timezone.utc)),
    (datetime(2026, 11, 12, 10, 30), datetime(2026, 11, 12, 10, 30, tzinfo=timezone.utc)),
    ("2026-11-12T10:30:00", datetime(2026, 11, 12, 10, 30, tzinfo=timezone.utc)),
])
def test_parse_iso_normalizes_supported_timestamps_to_utc(value, expected):
    assert parse_iso(value) == expected


def test_parse_iso_missing_invalid_and_unsupported_values():
    assert parse_iso(None) is None
    assert parse_iso("") is None
    with pytest.raises(ValueError, match="Invalid ISO-8601"):
        parse_iso("not a timestamp")
    with pytest.raises(TypeError, match="Timestamp must"):
        parse_iso(123)


def test_article_accepts_datetime_timestamps_directly():
    article = Article.from_raw({
        "article_id": "a", "ticker": "ABC", "title": "Headline",
        "published_at": datetime(2026, 11, 12, 12),
        "first_seen_at": datetime(2026, 11, 12, 15, tzinfo=timezone(timedelta(hours=3))),
    })
    assert article.published_at == datetime(2026, 11, 12, 12, tzinfo=timezone.utc)
    assert article.first_seen_at == datetime(2026, 11, 12, 12, tzinfo=timezone.utc)


def test_article_does_not_silently_discard_invalid_timestamp():
    with pytest.raises(ValueError, match="Invalid ISO-8601"):
        Article.from_raw({
            "article_id": "a", "ticker": "ABC", "title": "Headline",
            "published_at": "yesterday-ish",
        })
