"""Exponential event time decay with explicit timestamp validation."""

from dataclasses import dataclass
from datetime import datetime, timezone
from math import exp, log
import math
from pathlib import Path

import pandas as pd
import yaml

from models._records import as_record

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "decay.yaml"


@dataclass
class TimeDecayConfig:
    half_life_hours: float | None = None
    timestamp_fields: tuple[str, ...] | None = None
    missing_timestamp_weight: float | None = None
    config_path: str | Path | None = None

    def __post_init__(self):
        # Any omitted parameters come from config/decay.yaml, including when
        # callers construct TimeDecayConfig() directly.
        if any(value is None for value in (self.half_life_hours, self.timestamp_fields, self.missing_timestamp_weight)):
            path = Path(self.config_path or DEFAULT_CONFIG_PATH)
            with path.open(encoding="utf-8") as stream:
                values = yaml.safe_load(stream) or {}
            for name in ("half_life_hours", "timestamp_fields", "missing_timestamp_weight"):
                if getattr(self, name) is None:
                    value = values.get(name)
                    if name == "timestamp_fields" and value is not None:
                        value = tuple(value)
                    setattr(self, name, value)
        if self.half_life_hours is None or self.timestamp_fields is None or self.missing_timestamp_weight is None:
            raise ValueError("decay configuration must define all three parameters")
        if not math.isfinite(self.half_life_hours) or self.half_life_hours <= 0:
            raise ValueError("half_life_hours must be positive")
        if not math.isfinite(self.missing_timestamp_weight) or not 0 <= self.missing_timestamp_weight <= 1:
            raise ValueError("missing_timestamp_weight must be between 0 and 1")

    @classmethod
    def from_yaml(cls, path=DEFAULT_CONFIG_PATH):
        with Path(path).open(encoding="utf-8") as stream:
            values = yaml.safe_load(stream) or {}
        allowed = {"half_life_hours", "timestamp_fields", "missing_timestamp_weight"}
        unknown = set(values) - allowed
        if unknown:
            raise ValueError(f"Unknown decay configuration keys: {sorted(unknown)}")
        if "timestamp_fields" in values:
            values["timestamp_fields"] = tuple(values["timestamp_fields"])
        return cls(**values, config_path=path)


def _timestamp(event, fields):
    row = as_record(event)
    for field in fields:
        value = row.get(field)
        if value is None or value == "":
            continue
        try:
            stamp = pd.Timestamp(value)
            if pd.isna(stamp):
                continue
            if stamp.tzinfo is None:
                stamp = stamp.tz_localize("UTC")
            else:
                stamp = stamp.tz_convert("UTC")
            # Person 1's documented missing-date fallback is Unix epoch in 1970.
            if stamp.year == 1970:
                continue
            return stamp.to_pydatetime()
        except (TypeError, ValueError, OverflowError):
            continue
    return None


def calculate_time_weight(event, *, as_of=None, config=None):
    """Return a [0,1] exponential decay result and inspectable metadata."""
    cfg = config or TimeDecayConfig.from_yaml()
    now = as_of or datetime.now(timezone.utc)
    now = pd.Timestamp(now)
    now = now.tz_localize("UTC") if now.tzinfo is None else now.tz_convert("UTC")
    timestamp = _timestamp(event, cfg.timestamp_fields)
    if timestamp is None:
        age_hours = None
        weight = float(cfg.missing_timestamp_weight)
    else:
        age_hours = max(0.0, (now.to_pydatetime() - timestamp).total_seconds() / 3600.0)
        decay_lambda = log(2.0) / cfg.half_life_hours
        weight = exp(-decay_lambda * age_hours)
    return {
        "time_weight": min(1.0, max(0.0, weight)),
        "event_age_hours": age_hours,
        "lambda_used": log(2.0) / cfg.half_life_hours,
        "half_life_hours": cfg.half_life_hours,
        "timestamp_used": timestamp.isoformat() if timestamp else None,
    }


def time_weights_by_event(events, *, as_of=None, config=None):
    """Return time weights keyed by event ID, ready to merge with other scores."""
    output = {}
    for event in events:
        row = as_record(event)
        event_id = row.get("event_id")
        result = calculate_time_weight(event, as_of=as_of, config=config)
        output[event_id] = {"time_weight": result["time_weight"], "lambda_used": result["lambda_used"], "event_age": result["event_age_hours"], "timestamp_used": result["timestamp_used"]}
    return output
