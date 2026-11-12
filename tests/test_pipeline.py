from datetime import date
from pathlib import Path

import yaml

import pipeline as group1_pipeline
from collectors.base_collector import RawArticleRecord


def _config(tmp_path, **collector_settings):
    config = {
        "general": {"max_lookback_days": 14},
        "collectors": {
            "google_news_rss": {"enabled": True},
            "generic_rss": {"enabled": False},
            "nse_announcements": {"enabled": False},
            "bse_announcements": {"enabled": False},
            "sebi_releases": {"enabled": False},
            "company_ir": {"enabled": False},
        },
    }
    config["collectors"].update(collector_settings)
    path = tmp_path / "config.yaml"
    path.write_text(yaml.safe_dump(config), encoding="utf-8")
    return str(path)


def _record(profile):
    return RawArticleRecord(
        company_name=profile.company_name, ticker=profile.ticker,
        title="Contract fixture", description="Synthetic test coverage",
        url="https://example.test/item", source="Synthetic publisher",
        source_type="NEWS_RSS", primary_source=False,
        published_at=f"{date.today().isoformat()}T12:00:00Z",
        first_seen_at="2026-11-12T12:00:00Z", retrieved_at="2026-11-12T12:00:00Z",
        collector="fixture",
    ).model_dump()


def test_pipeline_passes_generated_queries_and_returns_contract_and_run_metadata(
    tmp_path, monkeypatch, sample_reliance_profile
):
    class Resolver:
        def __init__(self):
            pass

        def resolve(self, query):
            return sample_reliance_profile

    class Generator:
        def __init__(self):
            pass

        def generate(self, profile):
            return {"earnings": ["Reliance earnings"]}

        def get_flat_query_list(self, profile):
            return ["Reliance earnings", "Reliance board appointment"]

    captured = {}

    class Collector:
        name = "fake_search"

        def __init__(self, config=None):
            pass

        def collect_with_status(self, profile, start_date, end_date, queries):
            captured.update(start=start_date, end=end_date, queries=queries)
            return {"status": "success", "count": 1, "records": [_record(profile)],
                    "errors": [], "warnings": [], "unsupported_reason": None}

    monkeypatch.setattr(group1_pipeline, "EquityResolver", Resolver)
    monkeypatch.setattr(group1_pipeline, "QueryGenerator", Generator)
    monkeypatch.setattr(group1_pipeline, "GoogleNewsRSSCollector", Collector)
    config = _config(tmp_path)

    result = group1_pipeline.collect_equity_news("Reliance", config_path=config, run_id="test-run")
    assert result["collection_status"] == "success"
    assert captured["queries"] == ["Reliance earnings", "Reliance board appointment"]
    assert captured["start"].tzinfo is not None and captured["end"].tzinfo is not None
    required = {
        "ticker", "company_name", "title", "description", "url", "source",
        "source_type", "primary_source", "published_at", "first_seen_at", "retrieved_at",
    }
    assert required <= result["raw_articles"][0].keys()
    assert result["raw_articles"][0]["collector"] == "fixture"
    assert result["collection_run"]["run_id"] == "test-run"
    assert result["collection_run"]["completed_at"]


def test_pipeline_surfaces_partial_collector_failure(tmp_path, monkeypatch, sample_reliance_profile):
    class Resolver:
        def __init__(self): pass
        def resolve(self, query): return sample_reliance_profile

    class Generator:
        def __init__(self): pass
        def generate(self, profile): return {}
        def get_flat_query_list(self, profile): return []

    class Collector:
        name = "fake_search"
        def __init__(self, config=None): pass
        def collect_with_status(self, *args):
            return {"status": "failed", "count": 0, "records": [],
                    "errors": [{"collector": self.name, "error": "fixture network failure"}],
                    "warnings": [], "unsupported_reason": None}

    monkeypatch.setattr(group1_pipeline, "EquityResolver", Resolver)
    monkeypatch.setattr(group1_pipeline, "QueryGenerator", Generator)
    monkeypatch.setattr(group1_pipeline, "GoogleNewsRSSCollector", Collector)
    result = group1_pipeline.collect_equity_news("Reliance", config_path=_config(tmp_path))
    assert result["collection_status"] == "failed"
    assert result["errors"][0]["error"] == "fixture network failure"
    assert result["collector_results"]["fake_search"]["status"] == "failed"


def test_pipeline_rejects_invalid_date_window_before_collection(tmp_path, monkeypatch, sample_reliance_profile):
    class NeverResolver:
        def __init__(self):
            raise AssertionError("invalid dates must fail before resolver construction")

    monkeypatch.setattr(group1_pipeline, "EquityResolver", NeverResolver)
    result = group1_pipeline.collect_equity_news(
        "Reliance", start_date="not-a-date", config_path=_config(tmp_path)
    )
    assert result["collection_status"] == "failed"
    assert result["errors"][0]["stage"] == "date_window"
