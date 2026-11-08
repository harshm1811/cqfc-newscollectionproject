"""Configurable, missing-aware event importance scoring.

Inputs absent from Person 1's current Event schema (financial magnitude,
novelty, quantitative information, breaking status, and company specificity)
must be supplied by Group 2 or another enrichment step. Unavailable factors
are excluded and the remaining weights are renormalized; they are never
silently assigned a score.
"""

from dataclasses import dataclass
from pathlib import Path
from collections.abc import Mapping
import math

import yaml

from ._records import as_record, get_value

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "importance.yaml"
FACTOR_ALIASES = {
    "event_type": ("event_type_score",),
    "financial_magnitude": ("financial_magnitude", "magnitude_score"),
    "independent_source_count": ("independent_source_count",),
    "primary_source_confirmation": ("primary_source_confirmed", "primary_source_confirmation"),
    "company_specificity": ("company_specificity", "company_specificity_score"),
    "novelty": ("novelty", "novelty_score"),
    "quantitative_information": ("quantitative_information", "quantitative_information_score"),
    "breaking_news_status": ("breaking_news_status", "is_breaking", "breaking_news"),
}


@dataclass
class ImportanceConfig:
    factor_weights: dict | None = None
    event_type_scores: dict | None = None
    independent_source_count_saturation: int | None = None
    config_path: str | Path | None = None


def _load_config(config):
    path = config.config_path if config and config.config_path else DEFAULT_CONFIG_PATH
    with Path(path).open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if config:
        if config.factor_weights is not None:
            data["factor_weights"] = config.factor_weights
        if config.event_type_scores is not None:
            data["event_type_scores"] = config.event_type_scores
        if config.independent_source_count_saturation is not None:
            data["independent_source_count_saturation"] = config.independent_source_count_saturation
    weights = data.get("factor_weights", {})
    required = set(FACTOR_ALIASES)
    if set(weights) != required:
        raise ValueError(f"factor_weights must contain exactly: {sorted(required)}")
    if any(not isinstance(v, (int, float)) or v < 0 for v in weights.values()):
        raise ValueError("factor weights must be non-negative numbers")
    if not math.isclose(sum(weights.values()), 1.0, abs_tol=1e-8):
        raise ValueError("factor weights must sum to 1")
    return data


def score_event_importance(event, *, config=None, additional_factors: Mapping | None = None):
    """Return score, factor diagnostics, and missing-factor names for an event."""
    row = as_record(event)
    cfg = _load_config(config)
    external = dict(additional_factors or {})
    factors, missing = {}, []
    for name, aliases in FACTOR_ALIASES.items():
        value = external.get(name)
        if value is None:
            value = get_value(event, *aliases)
        if name == "event_type" and value is None:
            kind = get_value(event, "event_type", "type")
            scores = cfg.get("event_type_scores", {})
            type_scores = get_value(event, "type_scores", default={}) or {}
            value = type_scores.get(str(kind).casefold()) if kind is not None and isinstance(type_scores, Mapping) else None
            if value is None:
                value = scores.get(str(kind).casefold()) if kind is not None else None
        if name == "independent_source_count" and value is not None:
            saturation = max(1, int(cfg.get("independent_source_count_saturation", 5)))
            try:
                value = min(max(float(value), 0.0) / saturation, 1.0)
            except (TypeError, ValueError):
                value = None
        elif name in ("primary_source_confirmation", "breaking_news_status") and value is not None:
            value = 1.0 if bool(value) else 0.0
        try:
            score = float(value) if value is not None else None
        except (TypeError, ValueError):
            score = None
        if score is None or not math.isfinite(score):
            factors[name] = None
            missing.append(name)
        else:
            factors[name] = min(1.0, max(0.0, score))
    available_weight = sum(cfg["factor_weights"][k] for k, v in factors.items() if v is not None)
    result = (sum(cfg["factor_weights"][k] * v for k, v in factors.items() if v is not None) / available_weight
              if available_weight else None)
    return {
        "event_id": row.get("event_id"),
        "importance_score": result,
        "importance_components": factors,
        "missing_factors": missing,
        "available_weight": available_weight,
    }
