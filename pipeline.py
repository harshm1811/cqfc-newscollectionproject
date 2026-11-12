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
from models.sentiment import (FinBERTSentimentModel, LexiconSentimentModel,
                              SentimentConfig, SentimentModel,
                              aggregate_event_sentiment, resolve_sentiment_model,
                              score_articles)
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
    sentiment_model_name: Optional[str] = None
    sentiment_fallback_reason: Optional[str] = None

    @property
    def events_df(self) -> pd.DataFrame:
        return pd.DataFrame(self.event_records)


def default_sentiment_model(config: Optional[SentimentConfig] = None) -> SentimentModel:
    """Return an initialized FinBERT model, or its explicitly configured fallback."""
    return resolve_sentiment_model(config)[0]


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
    sentiment_config: Optional[SentimentConfig] = None,
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
    articles = [Article.from_raw(a) for a in raw_articles]
    if not articles:
        return Group3PipelineResult(
            events=[],
            event_records=[],
            daily_features=pd.DataFrame(),
            articles=[],
            mappings=[],
        )

    # 2. Score article sentiment
    if sentiment_model is None:
        model, fallback_reason = resolve_sentiment_model(sentiment_config)
    elif isinstance(sentiment_model, FinBERTSentimentModel):
        config = sentiment_config or SentimentConfig.from_env()
        try:
            sentiment_model.ensure_loaded()
            model, fallback_reason = sentiment_model, None
            logger.warning("Using FinBERT model %s", model.model_name)
        except Exception as exc:
            fallback_reason = f"FinBERT initialization failed ({type(exc).__name__}): {exc}"
            if not config.fallback_enabled:
                raise RuntimeError(fallback_reason + "; lexicon fallback is disabled") from exc
            model = LexiconSentimentModel()
            logger.warning("Using %s because %s", model.name, fallback_reason)
    else:
        model, fallback_reason = sentiment_model, None
        logger.warning("Using explicitly supplied sentiment model %s", model.name)
    try:
        articles = score_articles(articles, model)
    except Exception as exc:
        if isinstance(model, FinBERTSentimentModel):
            config = sentiment_config or SentimentConfig.from_env()
            fallback_reason = f"FinBERT inference failed ({type(exc).__name__}): {exc}"
            if config.fallback_enabled:
                model = LexiconSentimentModel()
                logger.warning("Using %s because %s; rescoring the complete article batch", model.name, fallback_reason)
                try:
                    articles = score_articles(articles, model)
                except Exception as fallback_exc:
                    raise RuntimeError(
                        f"Lexicon inference also failed after {fallback_reason}"
                    ) from fallback_exc
            else:
                raise RuntimeError(fallback_reason + "; lexicon fallback is disabled") from exc
        else:
            raise RuntimeError(
                f"Sentiment inference failed using {model.name}; no model switch was attempted"
            ) from exc

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

    # Preserve exact event scoring values and diagnostics in the downstream record.
    for ev in events:
        ev.sentiment_model_name = model.name
        if ev.event_id in event_scores:
            score = event_scores[ev.event_id]
            ev.importance_score = score.get("importance_score")
            ev.relevance_score = score.get("relevance_score")
            ev.source_quality = score.get("source_quality")
            ev.time_weight = score.get("time_weight")
            ev.final_event_weight = score.get("final_event_weight")
            ev.sentiment_contribution = score.get("sentiment_contribution")
            ev.source_quality_category = score.get("source_quality_category", [])
            ev.source_quality_breakdown = score.get("source_quality_breakdown", {})
            ev.importance_breakdown = score.get("importance_breakdown", {})
            ev.time_weight_breakdown = score.get("time_weight_breakdown", {})
            ev.weight_missing_inputs = score.get("weight_missing_inputs", [])

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
        sentiment_model_name=model.name,
        sentiment_fallback_reason=fallback_reason,
    )
