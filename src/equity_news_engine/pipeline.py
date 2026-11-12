"""Composable orchestration boundary for future Group 1–3 integrations."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable, Mapping

from .repository import Repository, RepositoryError
from .runs import RunTracker


class AdapterUnavailable(RuntimeError):
    """An upstream group's real implementation has not been connected."""


@dataclass
class StageOutcome:
    stage: str
    status: str
    input_count: int | None = None
    output_count: int | None = None
    error: str | None = None


@dataclass
class PipelineResult:
    run_id: str
    status: str
    payload: Any
    stages: list[StageOutcome] = field(default_factory=list)


StageHandler = Callable[[Any], Any]


class GroupAdapter:
    """Named integration adapter; callers provide the real stage handler."""

    def __init__(self, group: str, handler: StageHandler | None = None):
        self.group = group
        self.handler = handler

    def run(self, payload: Any) -> Any:
        if self.handler is None:
            raise AdapterUnavailable(f"{self.group} adapter is not connected to a confirmed implementation")
        return self.handler(payload)


class Group1Adapter(GroupAdapter):
    def __init__(self, handler: StageHandler | None = None):
        super().__init__("Group 1", handler)


class Group2Adapter(GroupAdapter):
    def __init__(self, handler: StageHandler | None = None):
        super().__init__("Group 2", handler)


class Group3Adapter(GroupAdapter):
    def __init__(self, handler: StageHandler | None = None):
        super().__init__("Group 3", handler)


class Group4Adapter(GroupAdapter):
    """Persistence boundary supplied by Group 4 after its input is confirmed."""

    def __init__(self, handler: StageHandler | None = None):
        super().__init__("Group 4", handler)


class PipelineOrchestrator:
    """Run explicitly supplied stages, persist output only through a real callback."""

    def __init__(self, adapters: list[GroupAdapter], *, tracker: RunTracker,
                 repository: Repository | None = None):
        self.adapters = adapters
        self.tracker = tracker
        self.repository = repository

    def run(self, payload: Any, *, ticker: str | None = None,
            start_time: str | None = None, end_time: str | None = None,
            configuration: Mapping[str, Any] | None = None) -> PipelineResult:
        run_id = self.tracker.start(ticker=ticker, start_time=start_time, end_time=end_time,
                                    configuration=configuration,
                                    collectors=[adapter.group for adapter in self.adapters])
        result = PipelineResult(run_id=run_id, status="running", payload=payload)
        current = payload
        try:
            supplied = {adapter.group: adapter for adapter in self.adapters}
            ordered = [supplied.get(name, GroupAdapter(name)) for name in ("Group 1", "Group 2", "Group 3", "Group 4")]
            for adapter in ordered:
                before = len(current) if isinstance(current, (list, tuple)) else None
                try:
                    current = adapter.run(current)
                except Exception as exc:
                    result.stages.append(StageOutcome(adapter.group, "failed", before, error=str(exc)))
                    failure = {"stage": adapter.group, "error": str(exc)}
                    status = "partial_failure" if any(s.status == "succeeded" for s in result.stages) else "failed"
                    self.tracker.finish(run_id, failures=[failure], status=status)
                    result.status = status
                    result.payload = current
                    return result
                after = len(current) if isinstance(current, (list, tuple)) else None
                result.stages.append(StageOutcome(adapter.group, "succeeded", before, after))
            result.status = "succeeded"
            result.payload = current
            self.tracker.finish(run_id, status="succeeded")
            return result
        except Exception as exc:
            # Preserve orchestration failures in the same audit trail.
            try:
                self.tracker.fail(run_id, "orchestration", exc)
            except RepositoryError:
                pass
            raise
