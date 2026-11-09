"""
pipeline.py - Integrated End-to-End Pipeline for Group 3.

Flow:
  Clean Articles (Group 2)
      │
      ▼
  1. Financial Sentiment (FinBERT / Lexicon fallback)
      │
      ▼
  2. Event Clustering (TF-IDF / Embeddings)
      │
      ▼
  3. Event Classification (20 financial event categories)
      │
      ▼
  4. Importance, Source Quality & Time Decay Scoring
      │
      ▼
  5. Adaptation & Quant Feature Engineering (Rolling windows, shocks, volume, momentum)
      │
      ▼
  Group 4 Deliverables:
    - Event Dataset (list of event records / DataFrame)
    - Daily Feature Dataset (DataFrame)
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import pandas as pd

from events.event_clusterer import ClusteringConfig, EventClusterer
from events.event_model import Article, ArticleEventMapping, Event
from models.event_classifier import EventClassifier, KeywordRuleClassifier
from models.importance import ImportanceConfig
from models.sentiment import FinBERTSentimentModel, LexiconSentimentModel, SentimentModel, aggregate_event_sentiment, score_articles
from models.source_quality import SourceQualityConfig
from aggregation.adapters.input_adapter import InputAdapterConfig, adapt_enriched_outputs
from aggregation.event_scoring import calculate_event_scores
from aggregation.feature_engine import FeatureConfig, build_feature_dataset, standardize_feature_columns
from aggregation.time_decay import TimeDecayConfig

logger = logging.getLogger("group3.pipeline")


@dataclass
class Group3PipelineResult:
    """Standardized output container for Group 3."""
    events: List[Event]
    event_records: List[Dict[str, Any]]
    daily_features: pd.DataFrame
    articles: List[Article]
    mappings: List[ArticleEventMapping]

    @property
    def events_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.event_records)


def default_sentiment_model() -> SentimentModel:
    """Return FinBERT if transformers/torch is installed, else Lexicon fallback."""
    try:
        import transformers  # noqa: F401
        return FinBERTSentimentModel()
    except Exception:
        logger.info("FinBERT dependencies not found; falling back to LexiconSentimentModel.")
        return LexiconSentimentModel()


def run_group3_pipeline(
    raw_articles: Sequence[Any],
    sentiment_model: Optional[SentimentModel] = None,
    classifier: Optional[EventClassifier] = None,
    clusterer: Optional[EventClusterer] = None,
    importance_config: Optional[ImportanceConfig] = None,
    source_quality_config: Optional[SourceQualityConfig] = None,
    time_decay_config: Optional[TimeDecayConfig] = None,
    feature_config: Optional[FeatureConfig] = None,
    as_of: Optional[datetime] = None,
    to_snake_case: bool = True,
    importance_factors_by_event: Optional[Dict[str, Dict[str, Any]]] = None,
) -> Group3PipelineResult:
    """
    Execute the full Group 3 pipeline from clean articles to events and quant features.

    Parameters:
        raw_articles: Clean article records (dicts, objects, or Article instances from Group 2).
        sentiment_model: NLP model for financial sentiment (defaults to FinBERT / Lexicon).
        classifier: Classifier for the 20 event categories (defaults to KeywordRuleClassifier).
        clusterer: Clustering algorithm (defaults to EventClusterer).
        importance_config: Importance factor weights and thresholds.
        source_quality_config: Source categorization and weights.
        time_decay_config: Exponential decay configuration.
        feature_config: Daily feature generation configuration.
        as_of: Reference timestamp for time decay (defaults to now UTC).
        to_snake_case: Whether to format daily feature columns in Group 4 snake_case.
        importance_factors_by_event: Optional extra factors (financial_magnitude, etc.).

    Returns:
        Group3PipelineResult containing events, event records, daily_features, articles, and mappings.
    """
    if as_of is None:
        as_of = datetime.now(timezone.utc)

    # 1. Normalize articles from Group 2
    articles = [Article.from_raw(a) if not isinstance(a, Article) else a for a in raw_articles]
    if not articles:
        return Group3PipelineResult(
            events=[],
            event_records=[],
            daily_features=pd.DataFrame(),
            articles=[],
            mappings=[],
        )

    # 2. Score article sentiment
    model = sentiment_model or default_sentiment_model()
    articles = score_articles(articles, model)

    # 3. Cluster articles into events
    evt_clusterer = clusterer or EventClusterer()
    events, mappings = evt_clusterer.cluster(articles)

    # 4. Classify events and aggregate event-level sentiment
    evt_classifier = classifier or KeywordRuleClassifier()
    by_id = {a.article_id: a for a in articles}
    for ev in events:
        arts = [by_id[i] for i in ev.article_ids if i in by_id]
        evt_classifier.classify_event(ev, arts)
        agg = aggregate_event_sentiment(arts)
        if agg:
            ev.positive_probability = agg["positive_probability"]
            ev.neutral_probability = agg["neutral_probability"]
            ev.negative_probability = agg["negative_probability"]
            ev.sentiment_score = agg["sentiment_score"]
            ev.independent_source_count = int(agg["independent_source_count"])
            ev.primary_source_confirmed = bool(agg["primary_source_confirmed"])

    # 5. Score event importance, source quality, and time decay
    event_scores = calculate_event_scores(
        events,
        articles,
        importance_factors_by_event=importance_factors_by_event,
        as_of=as_of,
        importance_config=importance_config,
        source_quality_config=source_quality_config,
        time_decay_config=time_decay_config,
    )

    # Populate importance_score back onto Event objects
    for ev in events:
        if ev.event_id in event_scores:
            ev.importance_score = event_scores[ev.event_id].get("importance_score")

    # 6. Adapt enriched outputs for feature engine
    adf, edf, mdf = adapt_enriched_outputs(
        articles,
        events,
        mappings,
        event_scores=event_scores,
    )

    # 7. Generate Daily Equity Feature Dataset
    daily_features = build_feature_dataset(adf, edf, mdf, config=feature_config)
    if to_snake_case and not daily_features.empty:
        daily_features = standardize_feature_columns(daily_features, to_snake_case=True)

    # 8. Prepare Group 4 Event Records
    event_records = [ev.to_group4_record() for ev in events]

    return Group3PipelineResult(
        events=events,
        event_records=event_records,
        daily_features=daily_features,
        articles=articles,
        mappings=mappings,
    )
