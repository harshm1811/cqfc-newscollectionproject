"""Source categorization and article/event source-quality scoring.

Configured weights are experimental assumptions that need validation against
historical outcomes. Different source labels are not treated as independent
unless the records explicitly identify independent reporting.
"""

from dataclasses import dataclass
from pathlib import Path
from collections import defaultdict

import yaml

from ._records import as_record, get_value

DEFAULT_CONFIG_PATH = Path(__file__).resolve().parents[1] / "config" / "source_quality.yaml"


@dataclass
class SourceQualityConfig:
    category_weights: dict | None = None
    source_type_categories: dict | None = None
    source_categories: dict | None = None
    primary_confirmation_bonus: float | None = None
    independent_confirmation_bonus: float | None = None
    config_path: str | Path | None = None


def _load_config(config):
    path = config.config_path if config and config.config_path else DEFAULT_CONFIG_PATH
    with Path(path).open(encoding="utf-8") as stream:
        data = yaml.safe_load(stream) or {}
    if config:
        for key in ("category_weights", "source_type_categories", "source_categories", "primary_confirmation_bonus", "independent_confirmation_bonus"):
            value = getattr(config, key)
            if value is not None:
                data[key] = value
    return data


def categorize_source(article, *, config=None):
    cfg, row = _load_config(config), as_record(article)
    source = str(row.get("source") or "").strip().casefold()
    source_type = str(row.get("source_type") or "").strip().casefold().replace(" ", "_")
    names = {str(k).strip().casefold(): v for k, v in cfg.get("source_categories", {}).items()}
    types = {str(k).strip().casefold(): v for k, v in cfg.get("source_type_categories", {}).items()}
    if source in names:
        return names[source]
    if source_type in types:
        return types[source_type]
    return "unknown"


def score_article_source_quality(article, *, config=None):
    cfg = _load_config(config)
    row = as_record(article)
    category = categorize_source(row, config=config)
    weights = cfg.get("category_weights", {})
    base = float(weights.get(category, weights.get("unknown", 0.5)))
    primary = bool(row.get("primary_source", False))
    independent = row.get("independent_source")
    bonus_primary = float(cfg.get("primary_confirmation_bonus", 0.05)) if primary else 0.0
    bonus_independent = float(cfg.get("independent_confirmation_bonus", 0.03)) if independent is True else 0.0
    score = min(1.0, max(0.0, base + bonus_primary + bonus_independent))
    return {
        "article_id": row.get("article_id"),
        "source_category": category,
        "source_quality": score,
        "source_quality_components": {
            "category_weight": base,
            "primary_source_bonus": bonus_primary,
            "explicit_independence_bonus": bonus_independent,
            "independence_known": independent is not None,
        },
    }


def aggregate_event_source_quality(event, articles, *, config=None):
    """Aggregate source quality without inferring independence from names.

    Syndicated copies sharing `syndication_id` count once. Otherwise only
    explicit `independent_source=True` records count toward corroboration.
    """
    cfg = _load_config(config)
    event_row = as_record(event)
    scored = [score_article_source_quality(a, config=config) for a in articles]
    rows = [as_record(a) for a in articles]
    by_id = {r.get("article_id"): r for r in rows}
    quality_by_id = {s.get("article_id"): s for s in scored}
    unique = {}
    for row in rows:
        key = row.get("syndication_id") or row.get("article_id")
        if key not in unique:
            unique[key] = row
    unique_rows = list(unique.values())
    qvalues = [quality_by_id[r.get("article_id")]["source_quality"] for r in unique_rows]
    base_quality = sum(qvalues) / len(qvalues) if qvalues else float(cfg.get("category_weights", {}).get("unknown", 0.5))
    confirmed = bool(event_row.get("primary_source_confirmed", False)) or any(bool(r.get("primary_source")) for r in unique_rows)
    explicit_independent = sum(r.get("independent_source") is True for r in unique_rows)
    primary_bonus = float(cfg.get("primary_confirmation_bonus", 0.05)) if confirmed else 0.0
    independent_bonus = float(cfg.get("independent_confirmation_bonus", 0.03)) if explicit_independent > 1 else 0.0
    final = min(1.0, base_quality + primary_bonus + independent_bonus)
    categories = sorted({quality_by_id[r.get("article_id")]["source_category"] for r in unique_rows})
    return {
        "event_id": event_row.get("event_id"),
        "source_quality": final,
        "source_category": categories[0] if len(categories) == 1 else categories,
        "source_quality_components": {
            "unique_article_count": len(unique_rows),
            "category_quality_mean": base_quality,
            "primary_source_confirmed": confirmed,
            "primary_confirmation_bonus": primary_bonus,
            "explicit_independent_source_count": explicit_independent,
            "independent_confirmation_bonus": independent_bonus,
            "categories": categories,
        },
    }


def score_events_source_quality(events, articles, article_event_ids=None, *, config=None):
    """Return Person 3-compatible fields keyed by event ID."""
    article_event_ids = article_event_ids or {}
    article_rows = [(as_record(a), a) for a in articles]
    output = {}
    for event in events:
        event_id = get_value(event, "event_id")
        ids = set(get_value(event, "article_ids", default=[]) or [])
        selected = [obj for row, obj in article_rows if row.get("article_id") in ids or article_event_ids.get(row.get("article_id")) == event_id]
        result = aggregate_event_source_quality(event, selected, config=config)
        output[event_id] = {"source_quality": result["source_quality"], "source_category": result["source_category"], "source_quality_components": result["source_quality_components"]}
    return output
