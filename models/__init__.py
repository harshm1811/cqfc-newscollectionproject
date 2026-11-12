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
    SentimentConfig,
    SentimentModel,
    aggregate_event_sentiment,
    resolve_sentiment_model,
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
    "SentimentConfig",
    "SentimentModel",
    "SourceQualityConfig",
    "aggregate_event_sentiment",
    "resolve_sentiment_model",
    "aggregate_event_source_quality",
    "categorize_source",
    "score_article_source_quality",
    "score_articles",
    "score_event_importance",
]
