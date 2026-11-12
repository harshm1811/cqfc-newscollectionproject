import pytest

from equity_news_engine.database import initialize_database
from equity_news_engine.repository import Repository, RepositoryError


def setup_repo(tmp_path):
    db = tmp_path / "repo.db"
    initialize_database(db)
    return Repository(db)


def test_save_get_filter_update_and_links(tmp_path):
    repo = setup_repo(tmp_path)
    repo.save("EQUITIES", {"ticker": "ABC", "company_name": "Confirmed Company"})
    repo.save("SOURCES", {"name": "Example source", "source_type": "wire"})
    repo.save("ARTICLES", {"article_id": "a1", "ticker": "ABC", "title": "Stored headline", "published_at": "2026-01-02T10:00:00Z"})
    repo.save("EVENTS", {"event_id": "e1", "ticker": "ABC", "headline": "Stored event", "timestamp": "2026-01-02T11:00:00Z"})
    repo.link_article_event("a1", "e1")
    repo.link_article_event("a1", "e1")
    assert repo.get("ARTICLES", "article_id", "a1")["title"] == "Stored headline"
    assert len(repo.linked_articles("e1")) == 1
    assert len(repo.list_records("ARTICLES", filters={"ticker": "ABC"}, start="2026-01-01", end="2026-01-03")) == 1
    assert repo.update("ARTICLES", "article_id", "a1", {"title": "Updated headline"})
    assert repo.get("ARTICLES", "article_id", "a1")["title"] == "Updated headline"


def test_repository_rejects_unsafe_identifiers_and_bad_json(tmp_path):
    repo = setup_repo(tmp_path)
    with pytest.raises(RepositoryError):
        repo.save("ARTICLES; DROP TABLE EQUITIES", {"article_id": "x"})
    with pytest.raises(RepositoryError):
        repo.save("COLLECTION_RUNS", {"run_id": "r1", "configuration_json": "{bad"})
    with pytest.raises(RepositoryError):
        repo.list_records("ARTICLES", filters={"title; DROP TABLE ARTICLES": "x"})
