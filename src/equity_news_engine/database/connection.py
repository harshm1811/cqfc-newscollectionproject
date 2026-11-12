"""SQLite connection management."""

from __future__ import annotations

import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator


def database_path() -> Path:
    """Return configured database path (defaults to project-root data folder)."""
    configured = os.environ.get("EQUITY_NEWS_DB")
    if configured:
        return Path(configured).expanduser().resolve()
    # connection.py -> database -> equity_news_engine -> src -> project root
    return Path(__file__).resolve().parents[3] / "data" / "equity_news.db"


@contextmanager
def connect(path: str | Path | None = None) -> Iterator[sqlite3.Connection]:
    """Open a SQLite connection with foreign keys enabled and safe transaction handling.

    A successful context commits; an exception rolls back. The connection always closes.
    """
    target = Path(path).expanduser().resolve() if path is not None else database_path()
    target.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(target)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    try:
        yield connection
        connection.commit()
    except Exception:
        connection.rollback()
        raise
    finally:
        connection.close()
