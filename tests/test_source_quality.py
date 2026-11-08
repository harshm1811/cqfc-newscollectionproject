from models.source_quality import aggregate_event_source_quality, categorize_source


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
    syndicated = aggregate_event_source_quality(
        {"event_id": "e2"},
        [
            {"article_id": "a3", "source": "Outlet A", "syndication_id": "wire-copy-1"},
            {"article_id": "a4", "source": "Outlet B", "syndication_id": "wire-copy-1"},
        ],
    )
    assert syndicated["source_quality_components"]["unique_article_count"] == 1
