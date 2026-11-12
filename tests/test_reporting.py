import json

from equity_news_engine.database import initialize_database
from equity_news_engine.reporting import (build_intelligence_report, export_csv,
                                           export_json, records_for_export)
from equity_news_engine.repository import Repository


def test_empty_exports_and_report_are_valid(tmp_path):
    db = tmp_path / "report.db"
    initialize_database(db)
    repo = Repository(db)
    assert records_for_export(repo, "articles") == []
    assert isinstance(export_csv([]), str)
    assert json.loads(export_json([])) == []
    report = build_intelligence_report(repo)
    assert report["data_status"] == "empty"
    assert report["record_counts"]["articles"] == 0


def test_exports_contain_only_stored_records(tmp_path):
    db = tmp_path / "report.db"
    initialize_database(db)
    repo = Repository(db)
    repo.save("EQUITIES", {"ticker": "ABC"})
    repo.save("ARTICLES", {"article_id": "a1", "ticker": "ABC", "title": "Real stored row", "published_at": "2026-01-10"})
    articles = records_for_export(repo, "articles", ticker="ABC", start="2026-01-01", end="2026-01-31")
    assert len(articles) == 1
    assert "Real stored row" in export_csv(articles)
    assert json.loads(export_json(articles))[0]["article_id"] == "a1"


def test_populated_event_and_feature_report_and_exports(tmp_path):
    db = tmp_path / "populated-report.db"
    initialize_database(db)
    repo = Repository(db)
    # Synthetic fixture values for tests; these are not real financial records.
    repo.save("EQUITIES", {"ticker": "TEST"})
    repo.save("EVENTS", {
        "event_id": "synthetic-event-1", "ticker": "TEST", "type": "synthetic_test_event",
        "timestamp": "2026-02-03T12:00:00Z", "headline": "Synthetic test event",
        "importance": 0.5, "article_count": 2, "source_count": 1,
    })
    repo.save("DAILY_FEATURES", {
        "ticker": "TEST", "feature_date": "2026-02-03",
        "feature_name": "synthetic_test_feature", "feature_value": 1.25,
    })

    report = build_intelligence_report(repo, ticker="TEST")
    assert report["data_status"] == "available"
    assert report["record_counts"]["events"] == 1
    assert report["record_counts"]["features"] == 1
    assert report["events"][0]["event_id"] == "synthetic-event-1"
    assert report["daily_features"][0]["feature_name"] == "synthetic_test_feature"

    event_records = records_for_export(repo, "events", ticker="TEST")
    feature_records = records_for_export(repo, "features", ticker="TEST")
    for records, csv_marker, json_key, json_marker in [
        (event_records, "Synthetic test event", "event_id", "synthetic-event-1"),
        (feature_records, "synthetic_test_feature", "feature_name", "synthetic_test_feature"),
    ]:
        csv_output = export_csv(records)
        json_output = export_json(records)
        assert csv_marker in csv_output
        assert json.loads(json_output)[0][json_key] == json_marker
