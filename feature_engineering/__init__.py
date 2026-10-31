"""Quantitative features derived from enriched article and event records."""

from .pipeline import FeatureConfig, build_feature_dataset

__all__ = ["FeatureConfig", "build_feature_dataset"]
