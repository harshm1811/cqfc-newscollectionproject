"""Processing package for Group 2."""
from .cleaner import clean_article_text, clean_text, deduplicate_paragraphs, remove_boilerplate
from .normalizer import normalize_article, normalize_articles, normalize_timestamp, normalize_url
from .relevance import RelevanceEngine, calculate_relevance_score
from .exact_deduplicator import ExactDeduplicator, make_cluster_id
from .semantic_deduplicator import SemanticDeduplicator

__all__ = [
    "clean_article_text",
    "clean_text",
    "deduplicate_paragraphs",
    "remove_boilerplate",
    "normalize_article",
    "normalize_articles",
    "normalize_timestamp",
    "normalize_url",
    "RelevanceEngine",
    "calculate_relevance_score",
    "ExactDeduplicator",
    "make_cluster_id",
    "SemanticDeduplicator",
]
