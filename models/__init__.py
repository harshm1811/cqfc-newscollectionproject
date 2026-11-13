"""Models package for text processing and event intelligence."""

from .embeddings import EmbeddingModel, cosine_similarity
from .event_classifier import (
    Classification,
    CompositeEventClassifier,
    EventClassifier,
    FinDeBERTaEventClassifier,
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
    "Classification", "CompositeEventClassifier", "EmbeddingModel", "EventClassifier",
    "FinBERTSentimentModel", "FinDeBERTaEventClassifier", "ImportanceConfig", "KeywordRuleClassifier",
    "LexiconSentimentModel", "SentimentEngine", "SentimentConfig", "SentimentModel",
    "SourceQualityConfig", "aggregate_event_sentiment", "aggregate_event_source_quality",
    "categorize_source", "cosine_similarity", "resolve_sentiment_model",
    "score_article_source_quality", "score_articles", "score_event_importance",
]
