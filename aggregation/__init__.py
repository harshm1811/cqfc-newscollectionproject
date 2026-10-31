"""Group 3 event aggregation and feature engineering APIs."""

from .time_decay import TimeDecayConfig, calculate_time_weight, time_weights_by_event
from .event_scoring import calculate_event_scores
from .feature_engine import FeatureConfig, build_feature_dataset
from .adapters import InputAdapterConfig, adapt_enriched_outputs

__all__ = [
    "FeatureConfig",
    "InputAdapterConfig",
    "TimeDecayConfig",
    "adapt_enriched_outputs",
    "build_feature_dataset",
    "calculate_event_scores",
    "calculate_time_weight",
    "time_weights_by_event",
]
