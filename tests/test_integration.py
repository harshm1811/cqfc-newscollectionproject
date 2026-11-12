"""Offline integration checks using synthetic records in isolated databases."""

import json
import group2_pipeline as group2_module

from group3_pipeline import run_group3_pipeline as run_group3
from models.event_classifier import KeywordRuleClassifier
from models.sentiment import LexiconSentimentModel
from models.embeddings import EmbeddingModel
from processing.semantic_deduplicator import SemanticDeduplicator

from equity_news_engine import integration as integration_module
from equity_news_engine.repository import Repository
from equity_news_engine.runs import RunTracker


def _synthetic_group1_result():
    records = []
    for index, (publisher, minute, title) in enumerate([
        ("BSE News Desk", "05", "Synthetic test company reports fixture profit growth"),
        ("Example Market Wire", "12", "Synthetic test company profit rises in test fixture"),
    ]):
        records.append({
            "ticker": "TEST",
            "company_name": "Synthetic Test Company",
            "title": title,
            "description": "Synthetic test-only fixture; not real financial information.",
            "url": f"https://publisher.example.test/story-{index}",
            "raw_url": f"https://news.google.com/example-{index}",
            "source": publisher,
            "source_type": "NEWS_RSS",
            "primary_source": False,
            "published_at": f"2026-11-10T10:{minute}:00Z",
            "first_seen_at": f"2026-11-10T10:{minute}:30Z",
            "retrieved_at": f"2026-11-10T10:{minute}:30Z",
            "collector": "synthetic_fixture",
        })
    return {
        "equity_profile": {"ticker": "TEST", "company_name": "Synthetic Test Company", "exchange": "TEST EXCHANGE", "country": "TEST COUNTRY"},
        "raw_articles": records,
        "total_articles": len(records),
        "collection_status": "success",
        "collector_results": {
            "synthetic_fixture": {"status": "success", "errors": [], "unsupported_reason": None}
        },
        "errors": [],
    }


def _mock_group3(articles):
    return run_group3(
        articles,
        sentiment_model=LexiconSentimentModel(),
        classifier=KeywordRuleClassifier(),
    )


def test_synthetic_records_flow_through_groups_1_to_4(tmp_path, monkeypatch):
    monkeypatch.setattr(
        integration_module, "collect_equity_news", lambda *args, **kwargs: _synthetic_group1_result()
    )
    monkeypatch.setattr(integration_module, "run_group3_pipeline", _mock_group3)
    real_semantic_deduplicator = group2_module.SemanticDeduplicator

    class OfflineSemanticDeduplicator(real_semantic_deduplicator):
        def __init__(self, *, similarity_threshold):
            super().__init__(
                similarity_threshold=similarity_threshold,
                embedding_model=EmbeddingModel(force_fallback=True),
            )

    monkeypatch.setattr(group2_module, "SemanticDeduplicator", OfflineSemanticDeduplicator)
    db_path = tmp_path / "integration.sqlite"

    result = integration_module.run_equity_intelligence(
        "Synthetic Test Company", db_path=db_path
    )

    assert result["status"] == "succeeded"
    assert result["raw_article_count"] == 2
    assert result["processed_article_count"] == 2
    assert result["event_count"] >= 1
    assert result["daily_feature_value_count"] > 0

    repository = Repository(db_path)
    equity = repository.get("EQUITIES", "ticker", "TEST")
    assert equity["exchange"] == "TEST EXCHANGE"
    assert equity["country"] == "TEST COUNTRY"
    articles = repository.list_records("ARTICLES", filters={"ticker": "TEST"})
    assert len(articles) == 2
    assert all(article["retrieved_at"] for article in articles)
    assert all(article["primary_source"] == 0 for article in articles)
    assert all(article["independent_source"] == 1 for article in articles)
    sources = repository.list_records("SOURCES")
    bse_coverage = next(source for source in sources if source["name"].startswith("BSE News Desk"))
    assert bse_coverage["source_type"] == "NEWS_RSS"
    assert bse_coverage["primary_source"] == 0
    events = repository.list_records("EVENTS", filters={"ticker": "TEST"})
    assert events
    assert all(event["independent_source_count"] >= 1 for event in events)
    assert repository.list_records("DAILY_FEATURES", filters={"ticker": "TEST"})
    assert repository.sentiment_records(ticker="TEST")

    run = RunTracker(db_path).get(result["run_id"])
    assert run["status"] == "succeeded"
    assert run["article_count"] == 2
    assert run["event_count"] == result["event_count"]
    assert json.loads(run["model_versions_json"])["sentiment"]
    assert json.loads(run["model_versions_json"])["group2_embedding"] == "fallback"


def test_partial_group1_failure_is_retained_in_run_tracking(tmp_path, monkeypatch):
    group1 = _synthetic_group1_result()
    group1["collection_status"] = "partially_successful"
    group1["collector_results"]["failed_feed"] = {
        "status": "failed",
        "errors": [{"collector": "failed_feed", "operation": "http", "error": "fixture timeout"}],
        "unsupported_reason": None,
    }
    monkeypatch.setattr(integration_module, "collect_equity_news", lambda *args, **kwargs: group1)
    monkeypatch.setattr(integration_module, "run_group3_pipeline", _mock_group3)
    real_semantic_deduplicator = group2_module.SemanticDeduplicator

    class OfflineSemanticDeduplicator(real_semantic_deduplicator):
        def __init__(self, *, similarity_threshold):
            super().__init__(
                similarity_threshold=similarity_threshold,
                embedding_model=EmbeddingModel(force_fallback=True),
            )

    monkeypatch.setattr(group2_module, "SemanticDeduplicator", OfflineSemanticDeduplicator)
    db_path = tmp_path / "partial.sqlite"

    result = integration_module.run_equity_intelligence("Synthetic Test Company", db_path=db_path)

    assert result["status"] == "partial_failure"
    assert any(failure.get("error") == "fixture timeout" for failure in result["failures"])
    run = RunTracker(db_path).get(result["run_id"])
    assert run["failure_count"] >= 1
    assert run["article_count"] == 2
