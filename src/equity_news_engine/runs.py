"""Collection-run lifecycle and failure tracking."""

from __future__ import annotations

import json
import sqlite3
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from .database.connection import connect
from .repository import Repository, RepositoryError


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


class RunTracker:
    """Creates and updates auditable collection run records."""

    def __init__(self, db_path: str | Path | None = None):
        self.repository = Repository(db_path)
        self.db_path = db_path

    def start(self, *, ticker: str | None, start_time: str | None, end_time: str | None,
              configuration: Mapping[str, Any] | None = None,
              collectors: list[str] | None = None,
              model_versions: Mapping[str, str] | None = None,
              run_id: str | None = None) -> str:
        """Create a running record and return its unique ID."""
        parsed: list[datetime | None] = []
        for value in (start_time, end_time):
            if value is None:
                parsed.append(None)
                continue
            if not isinstance(value, str):
                raise ValueError("Run window values must be ISO-8601 strings or None")
            try:
                parsed.append(datetime.fromisoformat(value.replace("Z", "+00:00")))
            except ValueError as exc:
                raise ValueError(f"Invalid ISO-8601 run window value: {value}") from exc
        if parsed[0] and parsed[1]:
            left, right = parsed
            if left.tzinfo is None and right.tzinfo is not None:
                left = left.replace(tzinfo=right.tzinfo)
            if right.tzinfo is None and left.tzinfo is not None:
                right = right.replace(tzinfo=left.tzinfo)
            if left > right:
                raise ValueError("Run start time must not be after end time")
        identifier = run_id or str(uuid.uuid4())
        self.repository.save("COLLECTION_RUNS", {
            "run_id": identifier, "requested_ticker": ticker,
            "start_time": start_time, "end_time": end_time,
            "configuration_json": dict(configuration or {}),
            "collectors_json": collectors or [],
            "model_versions_json": dict(model_versions or {}),
            "status": "running",
        })
        return identifier

    def finish(self, run_id: str, *, article_count: int = 0, event_count: int = 0,
               failures: list[Mapping[str, Any]] | None = None,
               status: str | None = None) -> None:
        """Finish a run; failures result in partial_failure unless nothing succeeded."""
        failure_list = [dict(item) for item in (failures or [])]
        if min(article_count, event_count) < 0:
            raise ValueError("Record counts cannot be negative")
        if status is None:
            status = "partial_failure" if failure_list else "succeeded"
        if status not in {"succeeded", "partial_failure", "failed"}:
            raise ValueError("Final status must be succeeded, partial_failure, or failed")
        if status == "succeeded" and failure_list:
            raise ValueError("A run with failures cannot be marked succeeded")
        updated = self.repository.update("COLLECTION_RUNS", "run_id", run_id, {
            "end_time": utc_now(), "status": status,
            "article_count": article_count, "event_count": event_count,
            "failure_count": len(failure_list), "failures_json": failure_list,
        })
        if not updated:
            raise RepositoryError(f"Unknown run ID: {run_id}")

    def get(self, run_id: str) -> dict[str, Any] | None:
        return self.repository.get("COLLECTION_RUNS", "run_id", run_id)

    def fail(self, run_id: str, stage: str, error: BaseException | str) -> None:
        """Append failure details and set failed status without losing prior failures."""
        current = self.get(run_id)
        if current is None:
            raise RepositoryError(f"Unknown run ID: {run_id}")
        failures = json.loads(current["failures_json"] or "[]")
        failures.append({"stage": stage, "error": str(error), "recorded_at": utc_now()})
        try:
            with connect(self.db_path) as connection:
                connection.execute("UPDATE COLLECTION_RUNS SET end_time = ?, status = 'failed', failure_count = ?, failures_json = ? WHERE run_id = ?",
                                   (utc_now(), len(failures), json.dumps(failures), run_id))
        except sqlite3.Error as exc:
            raise RepositoryError(f"Could not record run failure: {exc}") from exc
