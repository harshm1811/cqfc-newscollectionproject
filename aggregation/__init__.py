"""Group 3 event aggregation and feature engineering APIs."""

from .time_decay import TimeDecayConfig, calculate_time_weight, time_weights_by_event
from .event_scoring import calculate_event_scores
from .feature_engine import (
    FeatureConfig,
    PASCAL_TO_SNAKE_COLUMNS,
    build_feature_dataset,
    standardize_feature_columns,
)
from .adapters import InputAdapterConfig, adapt_enriched_outputs

__all__ = [
    "FeatureConfig",
    "InputAdapterConfig",
    "PASCAL_TO_SNAKE_COLUMNS",
    "TimeDecayConfig",
    "adapt_enriched_outputs",
    "build_feature_dataset",
    "calculate_event_scores",
    "calculate_time_weight",
    "standardize_feature_columns",
    "time_weights_by_event",
]
