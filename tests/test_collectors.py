"""
test_collectors.py - Unit Tests for RSS and Primary Collectors (Person B & Person C)

Test coverage goals:
1. Verify collectors return RawArticleRecord objects matching standard schema.
2. Verify primary_source = True for NSE/BSE/SEBI, False for RSS feeds.
3. Verify timestamp parsing conforms to UTC ISO-8601 (or None).
4. Verify raw responses are saved to data/raw/{ticker}/ without error.
5. All tests must run offline using saved XML / JSON payloads.
"""

import pytest
from collectors.base_collector import RawArticleRecord
from utils.timestamp_parser import parse_to_utc_iso


def test_raw_article_record_schema():
    record = RawArticleRecord(
        company_name="Reliance Industries Limited",
        ticker="RELIANCE",
        title="Test Headline",
        description="Test Description",
        url="https://example.com/test",
        source="Test Source",
        source_type="NEWS_RSS",
        primary_source=False,
        published_at="2026-10-28T10:00:00Z",
        first_seen_at="2026-10-28T10:05:00Z",
        retrieved_at="2026-10-28T10:05:00Z",
        collector="TestCollector"
    )
    assert record.ticker == "RELIANCE"
    assert record.primary_source is False


def test_timestamp_parser_valid():
    dt = parse_to_utc_iso("Mon, 27 Oct 2026 14:30:00 GMT")
    assert dt == "2026-10-27T14:30:00Z"


def test_timestamp_parser_invalid_never_invents_date():
    assert parse_to_utc_iso(None) is None
    assert parse_to_utc_iso("") is None
    assert parse_to_utc_iso("invalid date string") is None
