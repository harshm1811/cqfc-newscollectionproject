"""End-to-end integration test for Group 3 pipeline."""

from datetime import datetime, timezone
import pytest
import pandas as pd

from group3_pipeline import run_group3_pipeline, Group3PipelineResult
from models.sentiment import LexiconSentimentModel
from models.event_classifier import KeywordRuleClassifier


def test_full_group3_pipeline_with_group2_mock_data():
    """Test full flow: Group 2 Clean Articles -> Group 3 Pipeline -> Group 4 Outputs."""
    # Mock data strictly conforming to Group 2 -> Group 3 shared interface
    group2_articles = [
        {
            "article_id": "ART-001",
            "ticker": "RELIANCE",
            "title": "Reliance Q2 net profit rises 15% to Rs 19,000 crore",
            "clean_text": "Reliance Industries reported a 15% rise in quarterly net profit, beating street estimates.",
            "source": "BSE",
            "source_type": "EXCHANGE_FILING",
            "published_at": "2025-10-20T10:00:00Z",
            "first_seen_at": "2025-10-20T10:05:00Z",
            "relevance_score": 0.98,
            "duplicate_cluster_id": "CLUST-1",
            "primary_source": True,
            "independent_source": True,
        },
        {
            "article_id": "ART-002",
            "ticker": "RELIANCE",
            "title": "Reliance Industries Q2 profit surges on strong retail growth",
            "clean_text": "RIL posts strong Q2 earnings driven by expansion and retail numbers.",
            "source": "Mint",
            "source_type": "NEWS_RSS",
            "published_at": "2025-10-20T11:00:00Z",
            "first_seen_at": "2025-10-20T11:02:00Z",
            "relevance_score": 0.95,
            "duplicate_cluster_id": "CLUST-1",
            "primary_source": False,
            "independent_source": True,
        },
        {
            "article_id": "ART-003",
            "ticker": "RELIANCE",
            "title": "SEBI issues notice to Reliance over disclosure compliance",
            "clean_text": "Markets regulator SEBI initiated inquiry regarding disclosure norms.",
            "source": "SEBI",
            "source_type": "REGULATORY_ANNOUNCEMENT",
            "published_at": "2025-10-21T09:00:00Z",
            "first_seen_at": "2025-10-21T09:05:00Z",
            "relevance_score": 0.92,
            "duplicate_cluster_id": "CLUST-2",
            "primary_source": True,
            "independent_source": True,
        },
    ]

    as_of = datetime(2025, 10, 22, 12, 0, 0, tzinfo=timezone.utc)

    result = run_group3_pipeline(
        group2_articles,
        sentiment_model=LexiconSentimentModel(),
        classifier=KeywordRuleClassifier(),
        as_of=as_of,
        to_snake_case=True,
    )

    assert isinstance(result, Group3PipelineResult)
    assert len(result.articles) == 3
    assert len(result.events) == 2  # Q2 earnings event + SEBI regulatory event
    assert len(result.event_records) == 2

    # Check Group 4 Event Record schema adherence
    required_event_fields = {
        "event_id",
        "ticker",
        "event_type",
        "event_timestamp",
        "headline",
        "sentiment_score",
        "positive_probability",
        "neutral_probability",
        "negative_probability",
        "importance_score",
        "article_count",
        "independent_source_count",
        "primary_source_present",
    }
    for rec in result.event_records:
        assert required_event_fields.issubset(rec.keys())
        assert rec["ticker"] == "RELIANCE"
        assert -1.0 <= rec["sentiment_score"] <= 1.0
        assert 0.0 <= rec["importance_score"] <= 1.0
        prob_sum = rec["positive_probability"] + rec["neutral_probability"] + rec["negative_probability"]
        assert abs(prob_sum - 1.0) < 1e-4
        assert 0.0 <= rec["source_quality"] <= 1.0
        assert 0.0 <= rec["final_event_weight"] <= 1.0
        assert rec["source_quality_category"]
        assert "category_quality_mean" in rec["source_quality_breakdown"]

    # Check earnings event details
    earnings_event = next(e for e in result.events if e.article_count == 2)
    assert earnings_event.event_type.value == "EARNINGS"
    assert earnings_event.primary_source_confirmed is True
    assert earnings_event.independent_source_count == 2
    assert earnings_event.importance_score is not None

    # Check regulatory event details
    reg_event = next(e for e in result.events if e.article_count == 1)
    assert reg_event.event_type.value in ("REGULATION", "INVESTIGATION")

    # Check Daily Equity Feature Dataset schema adherence
    daily_df = result.daily_features
    assert not daily_df.empty
    assert "date" in daily_df.columns
    assert "ticker" in daily_df.columns

    # Verify snake_case standardized feature columns
    expected_cols = [
        "news_count",
        "unique_event_count",
        "positive_event_count",
        "negative_event_count",
        "weighted_sentiment",
        "sentiment_1d",
        "sentiment_3d",
        "sentiment_7d",
        "sentiment_30d",
        "sentiment_momentum",
        "news_volume_zscore",
        "positive_shock",
        "negative_shock",
        "mean_importance",
        "max_importance",
    ]
    for col in expected_cols:
        assert col in daily_df.columns

    # Check row values
    assert len(daily_df) >= 2  # 2 distinct dates: 2025-10-20 and 2025-10-21


def test_empty_pipeline_run():
    result = run_group3_pipeline([])
    assert len(result.events) == 0
    assert len(result.event_records) == 0
    assert result.daily_features.empty


def test_pipeline_with_pascal_case_and_custom_importance():
    articles = [
        {
            "article_id": "ART-101",
            "ticker": "INFY",
            "title": "Infosys declares special dividend of Rs 30 per share",
            "clean_text": "Infosys announces interim and special dividend payout.",
            "source": "NSE",
            "source_type": "EXCHANGE_FILING",
            "published_at": "2025-11-01T10:00:00Z",
            "primary_source": True,
            "relevance_score": 1.0,
        }
    ]
    result = run_group3_pipeline(
        articles,
        sentiment_model=LexiconSentimentModel(),
        to_snake_case=False,
    )
    assert len(result.events) == 1
    assert result.events[0].event_type.value == "DIVIDEND"
    # PascalCase column verification
    assert "NewsCount" in result.daily_features.columns
    assert "WeightedSentiment" in result.daily_features.columns


def test_article_from_raw_interface_compliance():
    from events.event_model import Article
    raw = {
        "article_id": "PRESERVED-ID-999",
        "ticker": "TCS",
        "company_name": "Tata Consultancy Services",
        "title": "TCS bags major cloud migration deal",
        "clean_text": "TCS signs contract with global bank.",
        "source": "Reuters",
        "source_type": "NEWS_RSS",
        "published_at": "2025-05-10T12:00:00Z",
        "first_seen_at": "2025-05-10T12:05:00Z",
        "relevance_score": 0.99,
        "duplicate_cluster_id": "DUP-42",
        "primary_source": False,
        "independent_source": True,
    }
    art = Article.from_raw(raw)
    assert art.article_id == "PRESERVED-ID-999"
    assert art.relevance_score == 0.99
    assert art.duplicate_cluster_id == "DUP-42"
    assert "cloud migration deal" in art.text
    assert art.independent_source is True
    d = art.to_dict()
    assert d["article_id"] == "PRESERVED-ID-999"
    assert d["relevance"] == 0.99
