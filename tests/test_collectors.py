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
from datetime import datetime, timezone
from collectors.base_collector import RawArticleRecord
from collectors.base_collector import BaseCollector
from collectors.bse_collector import BSECollector
from collectors.company_ir_collector import CompanyIRCollector
from collectors.google_news_rss import GoogleNewsRSSCollector
from collectors.nse_collector import NSECollector
from collectors.sebi_collector import SEBICollector
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
    required = {
        "ticker", "company_name", "title", "description", "url", "source",
        "source_type", "primary_source", "published_at", "first_seen_at", "retrieved_at",
    }
    assert required <= record.model_dump().keys()
    assert record.collector == "TestCollector"


def test_timestamp_parser_valid():
    dt = parse_to_utc_iso("Mon, 27 Oct 2026 14:30:00 GMT")
    assert dt == "2026-10-27T14:30:00Z"


def test_timestamp_parser_invalid_never_invents_date():
    assert parse_to_utc_iso(None) is None
    assert parse_to_utc_iso("") is None
    assert parse_to_utc_iso("invalid date string") is None


def test_naive_indian_exchange_timestamp_is_converted_from_ist():
    assert parse_to_utc_iso("28-Oct-2026 15:45:00") == "2026-10-28T10:15:00Z"


class _StatusCollector(BaseCollector):
    def __init__(self, mode):
        super().__init__("test", raw_data_dir=".")
        self.mode = mode

    def collect(self, profile, start_date=None, end_date=None, queries=None):
        if self.mode == "failed":
            raise RuntimeError("fixture failure")
        if self.mode == "partial":
            self.record_error("fixture_feed", "one feed failed")
        if self.mode in {"success", "partial", "dated"}:
            return [RawArticleRecord(
                company_name=profile.company_name, ticker=profile.ticker,
                title="Fixture headline", description="Fixture description",
                url="https://example.test/article", source="Fixture Publisher",
                source_type="NEWS_RSS", primary_source=False,
                published_at="2026-10-28T10:15:00Z",
                first_seen_at="2026-10-28T11:00:00Z",
                retrieved_at="2026-10-28T11:00:00Z", collector=self.name,
            )]
        return []


@pytest.mark.parametrize(("mode", "expected"), [
    ("success", "success"), ("empty", "no_results"),
    ("failed", "failed"), ("partial", "partially_successful"),
])
def test_collector_reports_success_empty_failure_and_partial(sample_reliance_profile, mode, expected):
    result = _StatusCollector(mode).collect_with_status(sample_reliance_profile)
    assert result["status"] == expected
    if mode == "partial":
        assert result["errors"][0]["error"] == "one feed failed"
    if mode == "success":
        assert result["records"][0]["primary_source"] is False


def test_date_window_filters_records_and_explains_undated_rows(sample_reliance_profile):
    collector = _StatusCollector("dated")
    result = collector.collect_with_status(
        sample_reliance_profile,
        datetime(2026, 10, 28, 10, 30, tzinfo=timezone.utc),
        datetime(2026, 10, 28, 12, 0, tzinfo=timezone.utc),
    )
    assert result["status"] == "no_results"
    assert result["count"] == 0


@pytest.mark.parametrize("collector_type,method_name", [
    (NSECollector, "_collect_from_announcement_feed"),
    (SEBICollector, "_collect_from_regulatory_feed"),
])
def test_google_fallback_is_secondary_and_keeps_publisher_and_url(
    tmp_path, sample_reliance_profile, monkeypatch, collector_type, method_name
):
    response = type("Response", (), {
        "status_code": 200,
        "text": '<rss><channel><item><title>Publisher report</title>'
                '<link>https://news.google.com/rss/articles/raw</link>'
                '<pubDate>Wed, 28 Oct 2026 10:15:00 GMT</pubDate>'
                '<description>Coverage summary</description><source>Actual Publisher</source>'
                '</item></channel></rss>',
    })()
    collector = collector_type(raw_data_dir=str(tmp_path))
    monkeypatch.setattr(collector.session, "get", lambda *a, **k: response)
    monkeypatch.setattr(
        f"collectors.{collector_type.__module__.split('.')[-1]}.resolve_google_redirect",
        lambda url, **kwargs: "https://publisher.test/story",
    )
    records = getattr(collector, method_name)(sample_reliance_profile.ticker, sample_reliance_profile.company_name)
    assert len(records) == 1
    record = records[0]
    assert record.primary_source is False
    assert record.source_type == "NEWS_RSS"
    assert record.source == "Actual Publisher"
    assert record.url == "https://publisher.test/story"
    assert record.raw_url == "https://news.google.com/rss/articles/raw"


def test_bse_without_verified_mapping_is_explicitly_unsupported(sample_reliance_profile, monkeypatch):
    collector = BSECollector()
    monkeypatch.setattr(collector.session, "get", lambda *a, **k: pytest.fail("must not issue an unmapped BSE request"))
    result = collector.collect_with_status(sample_reliance_profile)
    assert result["status"] == "unsupported"
    assert "verified six-digit BSE scrip-code mapping" in result["unsupported_reason"]


def test_google_collector_consumes_supplied_queries(sample_reliance_profile, monkeypatch):
    collector = GoogleNewsRSSCollector(config={"collectors": {"google_news_rss": {"max_queries": 2}}})
    seen = []
    monkeypatch.setattr(collector, "_fetch_rss", lambda url: seen.append(url) or [])
    collector.collect(sample_reliance_profile, queries=["revenue results", "board appointment", "ignored"])
    assert len(seen) == 2
    assert "revenue+results" in seen[0]
    assert "board+appointment" in seen[1]


def test_company_ir_without_config_is_unsupported(sample_reliance_profile):
    result = CompanyIRCollector().collect_with_status(sample_reliance_profile)
    assert result["status"] == "unsupported"
    assert "No company IR feed" in result["unsupported_reason"]


def test_company_ir_uses_explicit_configured_source(tmp_path, sample_reliance_profile, monkeypatch):
    config = {"collectors": {"company_ir": {"feeds_by_ticker": {
        "RELIANCE": [{"source": "Reliance Investor Relations",
                      "url": "https://ir.example.test/rss", "primary_source": True}]
    }}}}
    collector = CompanyIRCollector(raw_data_dir=str(tmp_path), config=config)
    response = type("Response", (), {
        "status_code": 200,
        "text": '<rss><channel><item><title>Official results</title>'
                '<link>https://ir.example.test/results</link>'
                '<pubDate>Wed, 28 Oct 2026 10:15:00 GMT</pubDate>'
                '<description>Company release</description></item></channel></rss>',
    })()
    monkeypatch.setattr(collector.session, "get", lambda *a, **k: response)
    result = collector.collect_with_status(sample_reliance_profile)
    assert result["status"] == "success"
    record = result["records"][0]
    assert record["source"] == "Reliance Investor Relations"
    assert record["source_type"] == "COMPANY_IR"
    assert record["primary_source"] is True
    assert record["url"] == "https://ir.example.test/results"
