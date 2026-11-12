"""
normalizer.py - Group 2 root module for backward compatibility and Member 1 normalization.
"""

from processing.normalizer import (
    KNOWN_PUBLISHERS,
    TRACKING_QUERY_PARAMS,
    normalize_article,
    normalize_articles,
    normalize_publisher,
    normalize_source_type,
    normalize_timestamp,
    normalize_url,
)

__all__ = [
    "KNOWN_PUBLISHERS",
    "TRACKING_QUERY_PARAMS",
    "normalize_article",
    "normalize_articles",
    "normalize_publisher",
    "normalize_source_type",
    "normalize_timestamp",
    "normalize_url",
]
