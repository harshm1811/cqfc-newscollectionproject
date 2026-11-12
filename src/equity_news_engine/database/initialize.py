"""Database schema initialization."""

from pathlib import Path

from .connection import connect

_SCHEMA_PATH = Path(__file__).with_name("schema.sql")


def initialize_database(path: str | Path | None = None) -> None:
    """Create the Group 4 schema and indexes if they do not already exist."""
    schema = _SCHEMA_PATH.read_text(encoding="utf-8")
    with connect(path) as connection:
        connection.executescript(schema)
