from models.source_quality import aggregate_event_source_quality, categorize_source
from models.source_quality import score_article_source_quality


def test_source_category_and_independence_are_explicit():
    assert categorize_source({"source": "NYSE", "source_type": "exchange"}) == "exchange_filing"
    result = aggregate_event_source_quality(
        {"event_id": "e1"},
        [
            {"article_id": "a1", "source": "Outlet A", "source_type": "publication"},
            {"article_id": "a2", "source": "Outlet B", "source_type": "publication"},
        ],
    )
    components = result["source_quality_components"]
    assert components["unique_article_count"] == 2
    assert components["explicit_independent_source_count"] == 0
    assert result["source_category"] == ["general_publication"]


def test_article_quality_excludes_event_confirmation_bonuses():
    from models.source_quality import score_article_source_quality
    row = {"article_id": "a", "source_type": "exchange", "primary_source": True, "independent_source": True}
    scored = score_article_source_quality(row)
    assert scored["source_quality"] == scored["source_quality_components"]["category_weight"]


def test_event_corroboration_bonuses_are_applied_once():
    result = aggregate_event_source_quality(
        {"event_id": "e", "primary_source_confirmed": True},
        [
            {"article_id": "a", "source": "Outlet A", "source_type": "publication", "primary_source": True, "independent_source": True},
            {"article_id": "b", "source": "Outlet B", "source_type": "publication", "independent_source": True},
        ],
    )
    assert result["source_category"] == ["general_publication"]
    assert abs(result["source_quality"] - 0.73) < 1e-9
    assert result["source_quality_components"]["primary_confirmation_bonus"] == 0.05
    assert result["source_quality_components"]["independent_confirmation_bonus"] == 0.03
    syndicated = aggregate_event_source_quality(
        {"event_id": "e2"},
        [
            {"article_id": "a3", "source": "Outlet A", "syndication_id": "wire-copy-1"},
            {"article_id": "a4", "source": "Outlet B", "syndication_id": "wire-copy-1"},
        ],
    )
    assert syndicated["source_quality_components"]["unique_article_count"] == 1


def test_source_type_and_publisher_hierarchy():
    assert categorize_source({"source": "Reuters", "source_type": "NEWS_RSS"}) == "major_financial_publication"
    assert categorize_source({"source": "Bloomberg", "source_type": "NEWS_RSS"}) == "major_financial_publication"
    for publisher in ("Mint", "Economic Times", "Business Standard"):
        assert categorize_source({"source": publisher, "source_type": "NEWS_RSS"}) == "recognized_indian_financial_publication"
    assert categorize_source({"source": "unknown outlet", "source_type": "NEWS_RSS"}) == "general_publication"
    assert categorize_source({"source": "unlisted", "source_type": "unlisted"}) == "unknown"
    assert score_article_source_quality({"source": "Reuters", "source_type": "NEWS_RSS"})["source_quality"] == 0.86
    assert score_article_source_quality({"source": "Mint", "source_type": "NEWS_RSS"})["source_quality"] == 0.82
    assert score_article_source_quality({"source": "unknown outlet", "source_type": "NEWS_RSS"})["source_quality"] == 0.65
    assert score_article_source_quality({"source": "unlisted", "source_type": "unlisted"})["source_quality"] == 0.50


def test_source_quality_bonus_is_capped_at_one():
    result = aggregate_event_source_quality(
        {"event_id": "cap", "primary_source_confirmed": True},
        [
            {"article_id": "a", "source": "company", "source_type": "company_announcement", "independent_source": True},
            {"article_id": "b", "source": "company", "source_type": "company_announcement", "independent_source": True},
        ],
    )
    assert result["source_quality"] == 1.0
