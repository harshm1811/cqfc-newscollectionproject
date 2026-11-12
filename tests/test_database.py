import sqlite3

import pytest

from equity_news_engine.database import connect, initialize_database


def test_initialization_creates_eight_tables_and_is_repeatable(tmp_path):
    db = tmp_path / "test.db"
    initialize_database(db)
    initialize_database(db)
    with connect(db) as connection:
        names = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert names == {
        "EQUITIES", "SOURCES", "ARTICLES", "EVENTS", "ARTICLE_EVENT_MAP",
        "SENTIMENT_RESULTS", "DAILY_FEATURES", "COLLECTION_RUNS",
    }


def test_foreign_keys_are_enforced(tmp_path):
    db = tmp_path / "test.db"
    initialize_database(db)
    with pytest.raises(sqlite3.IntegrityError):
        with connect(db) as connection:
            connection.execute(
                "INSERT INTO ARTICLES (article_id, ticker) VALUES (?, ?)",
                ("article-1", "UNKNOWN"),
            )


def test_transaction_rolls_back_on_error(tmp_path):
    db = tmp_path / "test.db"
    initialize_database(db)
    with pytest.raises(RuntimeError):
        with connect(db) as connection:
            connection.execute("INSERT INTO EQUITIES (ticker) VALUES ('TEST')")
            raise RuntimeError("force rollback")
    with connect(db) as connection:
        assert connection.execute("SELECT COUNT(*) FROM EQUITIES").fetchone()[0] == 0


def test_individual_schema_constraints_reject_invalid_records(tmp_path):
    db = tmp_path / "constraints.db"
    initialize_database(db)
    with connect(db) as connection:
        # These are synthetic test fixtures, isolated from the project database.
        connection.execute("INSERT INTO EQUITIES (ticker) VALUES ('TEST')")

    invalid_statements = [
        ("INSERT INTO EQUITIES (ticker) VALUES ('TEST')", ()),  # primary key
        ("INSERT INTO SOURCES (name, primary_source) VALUES (?, ?)", ("Synthetic source", 2)),
        ("INSERT INTO ARTICLES (article_id, ticker, relevance_score) VALUES (?, ?, ?)", ("bad-score", "TEST", 1.1)),
        ("INSERT INTO EVENTS (event_id, ticker, sentiment_score) VALUES (?, ?, ?)", ("bad-sentiment", "TEST", -1.1)),
        ("INSERT INTO EVENTS (event_id, ticker, importance) VALUES (?, ?, ?)", ("bad-importance", "TEST", 1.1)),
        ("INSERT INTO EVENTS (event_id, ticker, article_count) VALUES (?, ?, ?)", ("bad-count", "TEST", -1)),
        ("INSERT INTO EVENTS (event_id, ticker, sentiment_probabilities_json) VALUES (?, ?, ?)", ("bad-json", "TEST", "{bad")),
        ("INSERT INTO SENTIMENT_RESULTS (article_id, label) VALUES (?, ?)", (None, "unlinked")),
        ("INSERT INTO COLLECTION_RUNS (run_id, status) VALUES (?, ?)", ("bad-status", "unknown")),
        ("INSERT INTO COLLECTION_RUNS (run_id, article_count) VALUES (?, ?)", ("bad-run-count", -1)),
    ]
    for sql, params in invalid_statements:
        with pytest.raises(sqlite3.IntegrityError):
            with connect(db) as connection:
                connection.execute(sql, params)


def test_schema_creates_expected_lookup_indexes(tmp_path):
    db = tmp_path / "indexes.db"
    initialize_database(db)
    expected = {
        "idx_articles_ticker_published", "idx_articles_source",
        "idx_articles_duplicate_cluster", "idx_events_ticker_timestamp",
        "idx_article_event_event", "idx_sentiment_article", "idx_sentiment_event",
        "idx_daily_features_ticker_date", "idx_runs_ticker_created",
    }
    with connect(db) as connection:
        actual = {
            row[0]
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'index' AND name NOT LIKE 'sqlite_%'"
            )
        }
    assert expected <= actual
