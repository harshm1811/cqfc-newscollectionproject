"""Validated, centralized data access for the Group 4 SQLite store."""

from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any, Iterable, Mapping

from .database.connection import connect


class RepositoryError(ValueError):
    """Raised when repository input is invalid or a database operation fails."""


_TABLE_COLUMNS: dict[str, set[str]] = {
    "EQUITIES": {"ticker", "company_name", "exchange", "country"},
    "SOURCES": {"source_id", "name", "source_type", "primary_source"},
    "ARTICLES": {"article_id", "ticker", "source_id", "title", "description", "url", "published_at", "first_seen_at", "retrieved_at", "clean_text", "relevance_score", "duplicate_cluster_id", "primary_source", "independent_source", "independent_source_id"},
    "EVENTS": {"event_id", "ticker", "type", "timestamp", "headline", "sentiment_score", "sentiment_probabilities_json", "importance", "article_count", "source_count", "independent_source_count", "primary_source_present"},
    "SENTIMENT_RESULTS": {"sentiment_id", "article_id", "event_id", "model_version", "label", "score", "probabilities_json"},
    "DAILY_FEATURES": {"feature_id", "ticker", "feature_date", "feature_name", "feature_value", "source_run_id"},
    "COLLECTION_RUNS": {"run_id", "requested_ticker", "start_time", "end_time", "configuration_json", "collectors_json", "model_versions_json", "status", "article_count", "event_count", "failure_count", "failures_json", "created_at"},
}
_JSON_FIELDS = {"sentiment_probabilities_json", "probabilities_json", "configuration_json", "collectors_json", "model_versions_json", "failures_json"}


def _json_value(value: Any) -> str:
    try:
        return json.dumps(value, ensure_ascii=False, allow_nan=False)
    except (TypeError, ValueError) as exc:
        raise RepositoryError(f"Value is not valid JSON data: {exc}") from exc


class Repository:
    """CRUD operations for supported tables; all SQL stays behind this API."""

    def __init__(self, db_path: str | Path | None = None):
        self.db_path = Path(db_path) if db_path is not None else None

    def _connect(self):
        return connect(self.db_path)

    def save(self, table: str, record: Mapping[str, Any]) -> dict[str, Any]:
        """Insert one validated row and return its persisted values."""
        if table not in _TABLE_COLUMNS:
            raise RepositoryError(f"Unsupported table: {table}")
        values = dict(record)
        if not values or not set(values).issubset(_TABLE_COLUMNS[table]):
            raise RepositoryError(f"Invalid fields for {table}")
        for column in values.keys() & _JSON_FIELDS:
            if values[column] is not None and not isinstance(values[column], str):
                values[column] = _json_value(values[column])
            elif isinstance(values[column], str):
                try:
                    json.loads(values[column])
                except json.JSONDecodeError as exc:
                    raise RepositoryError(f"{column} must contain valid JSON") from exc
        columns = list(values)
        sql = f"INSERT INTO {table} ({', '.join(columns)}) VALUES ({', '.join('?' for _ in columns)})"
        try:
            with self._connect() as connection:
                cursor = connection.execute(sql, [values[c] for c in columns])
                if table == "SOURCES" and "source_id" not in values:
                    values["source_id"] = cursor.lastrowid
                elif table == "SENTIMENT_RESULTS" and "sentiment_id" not in values:
                    values["sentiment_id"] = cursor.lastrowid
                elif table == "DAILY_FEATURES" and "feature_id" not in values:
                    values["feature_id"] = cursor.lastrowid
            return values
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not save record to {table}: {exc}") from exc

    def get(self, table: str, key: str, value: Any) -> dict[str, Any] | None:
        """Retrieve a row by a supported key, or return None."""
        if table not in _TABLE_COLUMNS or key not in _TABLE_COLUMNS[table]:
            raise RepositoryError("Unsupported table or lookup key")
        try:
            with self._connect() as connection:
                row = connection.execute(f"SELECT * FROM {table} WHERE {key} = ?", (value,)).fetchone()
                return dict(row) if row else None
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not retrieve from {table}: {exc}") from exc

    def list_records(self, table: str, *, filters: Mapping[str, Any] | None = None,
                     start: str | None = None, end: str | None = None,
                     order_by: str | None = None, limit: int = 1000) -> list[dict[str, Any]]:
        """List rows with validated equality filters and standard date bounds."""
        if table not in _TABLE_COLUMNS:
            raise RepositoryError(f"Unsupported table: {table}")
        filters = dict(filters or {})
        if not set(filters).issubset(_TABLE_COLUMNS[table]):
            raise RepositoryError(f"Invalid filter for {table}")
        if not 1 <= limit <= 10000:
            raise RepositoryError("limit must be between 1 and 10000")
        date_column = {"ARTICLES": "published_at", "EVENTS": "timestamp", "DAILY_FEATURES": "feature_date", "COLLECTION_RUNS": "created_at"}.get(table)
        if (start or end) and not date_column:
            raise RepositoryError(f"Date filtering is not supported for {table}")
        clauses, params = [], []
        for column, value in filters.items():
            clauses.append(f"{column} = ?")
            params.append(value)
        if start:
            clauses.append(f"{date_column} >= ?")
            params.append(start)
        if end:
            clauses.append(f"{date_column} <= ?")
            params.append(end)
        ordering = order_by or (date_column if date_column else next(iter(_TABLE_COLUMNS[table])))
        if ordering not in _TABLE_COLUMNS[table]:
            raise RepositoryError(f"Invalid order column: {ordering}")
        where = f" WHERE {' AND '.join(clauses)}" if clauses else ""
        try:
            with self._connect() as connection:
                rows = connection.execute(f"SELECT * FROM {table}{where} ORDER BY {ordering} DESC LIMIT ?", (*params, limit)).fetchall()
                return [dict(row) for row in rows]
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not list {table}: {exc}") from exc

    def update(self, table: str, key: str, value: Any, changes: Mapping[str, Any]) -> bool:
        """Update a row using an allowlisted key and columns; return whether found."""
        if table not in _TABLE_COLUMNS or key not in _TABLE_COLUMNS[table]:
            raise RepositoryError("Unsupported table or update key")
        updates = dict(changes)
        if not updates or key in updates or not set(updates).issubset(_TABLE_COLUMNS[table]):
            raise RepositoryError("Invalid update fields")
        for column in updates.keys() & _JSON_FIELDS:
            if updates[column] is not None and not isinstance(updates[column], str):
                updates[column] = _json_value(updates[column])
        sql = f"UPDATE {table} SET {', '.join(f'{column} = ?' for column in updates)} WHERE {key} = ?"
        try:
            with self._connect() as connection:
                cursor = connection.execute(sql, (*updates.values(), value))
                return cursor.rowcount > 0
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not update {table}: {exc}") from exc

    def link_article_event(self, article_id: str, event_id: str) -> None:
        """Create an idempotent article-to-event relationship."""
        try:
            with self._connect() as connection:
                connection.execute("INSERT OR IGNORE INTO ARTICLE_EVENT_MAP (article_id, event_id) VALUES (?, ?)", (article_id, event_id))
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not link article and event: {exc}") from exc

    def linked_articles(self, event_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT a.* FROM ARTICLES a JOIN ARTICLE_EVENT_MAP m ON m.article_id = a.article_id WHERE m.event_id = ? ORDER BY a.published_at DESC", (event_id,)).fetchall()
            return [dict(row) for row in rows]

    def linked_events(self, article_id: str) -> list[dict[str, Any]]:
        with self._connect() as connection:
            rows = connection.execute("SELECT e.* FROM EVENTS e JOIN ARTICLE_EVENT_MAP m ON m.event_id = e.event_id WHERE m.article_id = ? ORDER BY e.timestamp DESC", (article_id,)).fetchall()
            return [dict(row) for row in rows]

    def sentiment_records(self, *, ticker: str | None = None, start: str | None = None,
                          end: str | None = None, limit: int = 10000) -> list[dict[str, Any]]:
        """Retrieve sentiment rows scoped through their linked article or event."""
        if not 1 <= limit <= 10000:
            raise RepositoryError("limit must be between 1 and 10000")
        clauses, params = [], []
        if ticker:
            clauses.append("(a.ticker = ? OR e.ticker = ?)")
            params.extend([ticker, ticker])
        if start:
            clauses.append("COALESCE(a.published_at, e.timestamp) >= ?")
            params.append(start)
        if end:
            clauses.append("COALESCE(a.published_at, e.timestamp) <= ?")
            params.append(end)
        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        with self._connect() as connection:
            rows = connection.execute(
                f"SELECT s.*, a.ticker AS article_ticker, e.ticker AS event_ticker, a.published_at, e.timestamp AS event_timestamp "
                f"FROM SENTIMENT_RESULTS s LEFT JOIN ARTICLES a ON a.article_id = s.article_id "
                f"LEFT JOIN EVENTS e ON e.event_id = s.event_id {where} ORDER BY s.created_at DESC LIMIT ?",
                (*params, limit),
            ).fetchall()
            return [dict(row) for row in rows]
