import json

from equity_news_engine.database import initialize_database
from equity_news_engine.pipeline import (Group1Adapter, Group2Adapter,
                                         Group3Adapter, Group4Adapter,
                                         PipelineOrchestrator)
from equity_news_engine.repository import Repository
from equity_news_engine.runs import RunTracker


def setup(tmp_path):
    db = tmp_path / "runs.db"
    initialize_database(db)
    repo = Repository(db)
    repo.save("EQUITIES", {"ticker": "ABC"})
    return db, repo


def test_run_tracking_records_configuration_counts_and_failures(tmp_path):
    db, repo = setup(tmp_path)
    tracker = RunTracker(db)
    run_id = tracker.start(ticker="ABC", start_time="2026-01-01", end_time="2026-01-31", configuration={"window": 30}, collectors=["collector"], model_versions={"model": "v1"})
    tracker.finish(run_id, article_count=3, event_count=2, failures=[{"stage": "Group 3", "error": "unavailable"}])
    record = tracker.get(run_id)
    assert record["status"] == "partial_failure"
    assert record["article_count"] == 3 and record["event_count"] == 2
    assert json.loads(record["configuration_json"]) == {"window": 30}
    assert json.loads(record["failures_json"])[0]["stage"] == "Group 3"


def test_pipeline_tracks_success_and_stops_at_unavailable_adapter(tmp_path):
    db, repo = setup(tmp_path)
    tracker = RunTracker(db)
    pipeline = PipelineOrchestrator([Group1Adapter(lambda rows: rows + ["collected"]), Group2Adapter()], tracker=tracker, repository=repo)
    outcome = pipeline.run([], ticker="ABC", start_time="2026-01-01", end_time="2026-01-02")
    assert outcome.status == "partial_failure"
    assert outcome.payload == ["collected"]
    assert outcome.stages[0].status == "succeeded"
    assert outcome.stages[1].status == "failed"
    run = tracker.get(outcome.run_id)
    assert run["status"] == "partial_failure"
    assert "not connected" in json.loads(run["failures_json"])[0]["error"]


def test_pipeline_can_run_confirmed_handlers(tmp_path):
    db, repo = setup(tmp_path)
    pipeline = PipelineOrchestrator([
        Group1Adapter(lambda text: text + "1"),
        Group2Adapter(lambda text: text + "2"),
        Group3Adapter(lambda text: text + "3"),
        Group4Adapter(lambda text: text + "4"),
    ], tracker=RunTracker(db))
    outcome = pipeline.run("", ticker="ABC")
    assert outcome.status == "succeeded"
    assert outcome.payload == "1234"


def test_run_tracker_rejects_reversed_window(tmp_path):
    db, repo = setup(tmp_path)
    tracker = RunTracker(db)
    import pytest
    with pytest.raises(ValueError, match="after end time"):
        tracker.start(ticker="ABC", start_time="2026-02-01", end_time="2026-01-01")
