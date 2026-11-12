from datetime import date
from pathlib import Path

from streamlit.testing.v1 import AppTest

from equity_news_engine.database import initialize_database
from equity_news_engine.repository import Repository


def test_all_dashboard_pages_render_with_empty_database(tmp_path, monkeypatch):
    db = tmp_path / "dashboard.db"
    monkeypatch.setenv("EQUITY_NEWS_DB", str(db))
    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    for page in ["Overview", "News Feed", "Events", "Sentiment", "Timeline", "Sources", "Export", "Search"]:
        app.radio[0].set_value(page).run()
        assert not app.exception, f"Page failed: {page}"


def test_all_dashboard_pages_render_with_populated_synthetic_records(tmp_path, monkeypatch):
    db = tmp_path / "dashboard-populated.db"
    monkeypatch.setenv("EQUITY_NEWS_DB", str(db))
    initialize_database(db)
    repo = Repository(db)
    fixture_date = date.today().isoformat()
    fixture_timestamp = f"{fixture_date}T10:00:00Z"
    # Synthetic fixtures validate populated UI states; they are not financial data.
    repo.save("EQUITIES", {"ticker": "TEST"})
    repo.save("SOURCES", {"name": "Synthetic test source", "source_type": "test"})
    repo.save("ARTICLES", {
        "article_id": "synthetic-article-1", "ticker": "TEST",
        "title": "Synthetic test article", "published_at": fixture_timestamp,
    })
    repo.save("EVENTS", {
        "event_id": "synthetic-event-1", "ticker": "TEST", "type": "synthetic_test_event",
        "timestamp": f"{fixture_date}T12:00:00Z", "headline": "Synthetic test event",
        "importance": 0.5,
    })
    repo.save("SENTIMENT_RESULTS", {
        "event_id": "synthetic-event-1", "label": "synthetic_test_label", "score": 0.25,
    })
    repo.save("DAILY_FEATURES", {
        "ticker": "TEST", "feature_date": fixture_date,
        "feature_name": "synthetic_test_feature", "feature_value": 1.25,
    })
    for name, value in (("weighted_sentiment", 0.42), ("sentiment_1d", 0.35),
                        ("sentiment_7d", 0.25), ("sentiment_30d", 0.15),
                        ("news_count", 1), ("unique_event_count", 1)):
        repo.save("DAILY_FEATURES", {
            "ticker": "TEST", "feature_date": fixture_date,
            "feature_name": name, "feature_value": value,
        })

    app = AppTest.from_file(Path(__file__).resolve().parents[1] / "app.py", default_timeout=20).run()
    assert not app.exception
    for page in ["Overview", "News Feed", "Events", "Sentiment", "Timeline", "Sources", "Export", "Search"]:
        app.radio[0].set_value(page).run()
        assert not app.exception, f"Populated page failed: {page}"
        if page == "News Feed":
            assert any("Synthetic test article" in item.value for item in app.markdown)
        elif page == "Events":
            assert any("Synthetic test event" in item.value for item in app.markdown)
        elif page == "Overview":
            assert any("Company sentiment series" in item.value for item in app.markdown)
            app.selectbox[0].set_value("TEST").run()
            assert {metric.label for metric in app.metric} >= {
                "Weighted sentiment", "24H sentiment", "7D sentiment", "30D sentiment",
            }
        elif page == "Search":
            assert "GENERATE ANALYSIS" in {button.label for button in app.button}
