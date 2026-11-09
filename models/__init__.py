"""Models package for event intelligence, scoring, sentiment, and classification."""

from .event_classifier import (
    Classification,
    CompositeEventClassifier,
    EventClassifier,
    KeywordRuleClassifier,
)
from .importance import ImportanceConfig, score_event_importance
from .sentiment import (
    FinBERTSentimentModel,
    LexiconSentimentModel,
    SentimentModel,
    aggregate_event_sentiment,
    score_articles,
)
from .source_quality import (
    SourceQualityConfig,
    aggregate_event_source_quality,
    categorize_source,
    score_article_source_quality,
)

SentimentEngine = FinBERTSentimentModel

__all__ = [
    "Classification",
    "CompositeEventClassifier",
    "EventClassifier",
    "FinBERTSentimentModel",
    "ImportanceConfig",
    "KeywordRuleClassifier",
    "LexiconSentimentModel",
    "SentimentEngine",
    "SentimentModel",
    "SourceQualityConfig",
    "aggregate_event_sentiment",
    "aggregate_event_source_quality",
    "categorize_source",
    "score_article_source_quality",
    "score_articles",
    "score_event_importance",
]
