"""Database schema initialization."""

from pathlib import Path

from .connection import connect

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def initialize_database(path: str | Path | None = None) -> None:
    """Create the schema and apply safe additive upgrades for existing databases."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(path) as connection:
        connection.executescript(schema)
        upgrades = {
            "EQUITIES": {"exchange": "TEXT", "country": "TEXT"},
            "ARTICLES": {
                "primary_source": "INTEGER CHECK (primary_source IS NULL OR primary_source IN (0, 1))",
                "independent_source": "INTEGER CHECK (independent_source IS NULL OR independent_source IN (0, 1))",
                "independent_source_id": "TEXT",
            },
            "EVENTS": {
                "independent_source_count": "INTEGER CHECK (independent_source_count IS NULL OR independent_source_count >= 0)",
                "primary_source_present": "INTEGER CHECK (primary_source_present IS NULL OR primary_source_present IN (0, 1))",
            },
        }
        for table, columns in upgrades.items():
            existing = {row[1] for row in connection.execute(f"PRAGMA table_info({table})")}
            for column, definition in columns.items():
                if column not in existing:
                    connection.execute(f"ALTER TABLE {table} ADD COLUMN {column} {definition}")
        connection.execute(
            "UPDATE ARTICLES SET primary_source = COALESCE((SELECT primary_source FROM SOURCES WHERE SOURCES.source_id = ARTICLES.source_id), 0) WHERE primary_source IS NULL"
        )
