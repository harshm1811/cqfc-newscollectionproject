# Equity News Intelligence & Sentiment Engine

Group 3 processes cleaned equity news into event-level scores and ticker/day
features. The code is divided by responsibility: Person 1 supplies event
classification and sentiment, Person 2 scores importance, source quality, and
time decay, and Person 3 adapts the enriched records and builds aggregate
features.

## Repository layout

```text
events/                         # Person 1's event model and clustering (to be added)
models/
  importance.py                 # Person 2 event importance scoring
  source_quality.py             # Person 2 source categorization and quality
  _records.py                   # Shared mapping/object conversion helpers
  sentiment.py                  # Person 1 sentiment (to be added)
  event_classifier.py           # Person 1 classification (to be added)
aggregation/
  event_scoring.py              # Person 2 combined event scores
  time_decay.py                 # Person 2 exponential time decay
  adapters/input_adapter.py     # Person 3 upstream-record adapter
  sentiment_index.py            # Person 3 event sentiment aggregation
  feature_engine.py             # Person 3 ticker/day feature pipeline
  rolling.py                    # Person 3 rolling sentiment and momentum
config/
  importance.yaml               # Importance weights and event-type scores
  source_quality.yaml           # Source categories and quality weights
  decay.yaml                    # Half-life and timestamp behavior
tests/                          # Group 3 unit and integration tests
```

Person 1's `events/` package and sentiment/classifier modules are not present in
this checkout. Person 2 and Person 3 modules accept dictionaries or compatible
record objects, so they do not import or redefine Person 1's models.

## Install and run

The runtime dependencies are Pandas, NumPy, and PyYAML. Pytest is included for
the test suite.

```bash
python -m pip install -r requirements.txt
python -m pytest -q
```

## End-to-end integration

Person 1's upstream stage is expected to provide article, event, and
article/event mapping records. Records may be dictionaries or objects exposing
`to_dict()` (or ordinary objects with attributes for the Person 2 scoring
functions).

```python
from datetime import datetime, timezone

from aggregation import (
    FeatureConfig,
    adapt_enriched_outputs,
    build_feature_dataset,
    calculate_event_scores,
)

# These collections come from the upstream event and sentiment stages.
articles, events, mappings = build_enriched_events(...)

# If Event.article_ids is unavailable, supply article_id -> event_id links.
article_event_ids = {"article-1": "event-1"}

# Supply factors that are not available on the upstream Event record.
# Values are normalized to [0, 1] by their producer.
importance_factors_by_event = {
    "event-1": {
        "financial_magnitude": 0.7,
        "company_specificity": 0.9,
        "novelty": 0.6,
        "quantitative_information": 0.8,
        "breaking_news_status": True,
    }
}

event_scores = calculate_event_scores(
    events,
    articles,
    article_event_ids=article_event_ids,
    importance_factors_by_event=importance_factors_by_event,
    as_of=datetime.now(timezone.utc),
)

article_df, event_df, mapping_df = adapt_enriched_outputs(
    articles,
    events,
    mappings,
    event_scores=event_scores,
    relevance_by_article={"article-1": 0.85},
)

daily = build_feature_dataset(
    article_df,
    event_df,
    mapping_df,
    config=FeatureConfig(volume_lookback=30),
)
```

`calculate_event_scores()` returns a mapping keyed by `event_id`. Each value
has exactly these adapter keys:

```python
{
    "importance_score": 0.88,
    "source_quality": 0.95,
    "time_weight": 0.85,
}
```

The adapter accepts this mapping as `event_scores`. Article-level relevance
is passed separately as `relevance_by_article`; the adapter averages mapped
article relevance to obtain event-level relevance for sentiment weighting.
The adapter also converts article and event timestamps to UTC, extracts
nested article sentiment, and retains article IDs, event IDs, and supplied
mappings.

## Person 2 scoring

### Event importance

`models/importance.py` combines eight factors: event type, financial magnitude,
independent source count, primary-source confirmation, company specificity,
novelty, quantitative information, and breaking-news status. Factor weights
must be non-negative and sum to one. The initial weights and event-type scores
are in `config/importance.yaml` and are configurable assumptions, not fitted
calibration.

The Person 1-style Event fields described for this project include event type,
independent source count, and primary-source confirmation. Other factors may
need to be supplied by Group 2 or another enrichment step through
`importance_factors_by_event`. Scores must be in `[0, 1]`; independent source
count is normalized using the configured saturation count. Missing factors
are reported by `score_event_importance()` and excluded before the remaining
weights are renormalized. If all factors are missing, `calculate_event_scores()`
raises a `ValueError` rather than inventing a score.

### Source quality

`models/source_quality.py` categorizes sources using `source` and
`source_type`. Supported categories are exchange filing, regulatory
announcement, official company announcement, investor relations, major
financial publication, general publication, aggregator, and unknown.
Category weights, source-type mappings, explicit source-name mappings, and
confirmation bonuses are configured in `config/source_quality.yaml`. These
starting weights are experimental assumptions that need validation.

Article quality is scored from its configured category, with optional primary
source and explicit independent-reporting signals. Event quality aggregates
the article scores and can account for `primary_source_confirmed`.
Syndicated copies with the same `syndication_id` count once. Different source
labels alone are not treated as independent reporting; corroboration uses
explicit `independent_source` metadata.

### Time decay

`aggregation/time_decay.py` computes an exponential time weight:

```text
time_weight = exp(-lambda * event_age_hours)
lambda = ln(2) / half_life_hours
```

The default half-life, timestamp fields, and missing-timestamp weight are
loaded from `config/decay.yaml`. Naive timestamps are interpreted as UTC;
timezone-aware timestamps are converted to UTC. Invalid and missing values
are skipped, and the documented 1970 fallback timestamp is treated as
missing. Future timestamps have age zero. The missing-timestamp weight is
configurable and currently defaults to `1.0`.

The individual scoring APIs return diagnostic components. The combined
`calculate_event_scores()` output stays limited to the three fields expected
by the Person 3 adapter.

## Person 3 feature pipeline

`aggregation.adapters.adapt_enriched_outputs()` converts upstream records to
article, event, and mapping DataFrames. Missing scores use visibly marked
mock defaults configured by `InputAdapterConfig`; provide real event scores
and article relevance for production use.

`aggregation.feature_engine.build_feature_dataset()` creates ticker/day rows.
`FeatureConfig` controls rolling windows, sentiment aggregation, volume
lookback, shock thresholds, the high-importance threshold, and sentiment
momentum windows.

The feature definitions are:

- Event contribution is `sentiment_score * relevance * importance_score * source_quality * time_weight`.
- `WeightedSentiment` is the weighted numerator divided by the sum of
  nonnegative event weights. It is a normalized weighted mean; zero total
  weight yields missing. `MeanSentiment` is the unweighted event mean.
- Each event contributes once to event-level counts and sentiment. Article
  IDs are counted independently for `NewsCount` and
  `RelevantArticleCount`.
- `Sentiment1D/3D/7D/30D` are trailing calendar-day averages including the
  current day. Missing dates are filled with zero sentiment. Tickers are
  processed separately in date order.
- `SentimentMomentum` is the configurable short-window minus long-window
  sentiment. Missing values default to zero unless configured to propagate.
- `NewsVolume` counts unique events per ticker/day.
  `NewsVolumeZScore` compares current volume with preceding observed daily
  rows, excluding the current row; it uses sample standard deviation.
- Positive, negative, and neutral counts use event sentiment sign. Shock
  flags use configured sentiment cutoffs. High-importance counts combine
  the configured importance cutoff with sentiment sign.
- `MeanImportance` and `MaxImportance` summarize daily event importance.
  `SourceAgreement` is one minus the population standard deviation of unique
  article sentiment scores across source labels per event, clipped to `[0,1]`
  and averaged by ticker/day. `SentimentDispersion` is the population
  standard deviation of unique event sentiment. `PrimarySourceEventCount`
  counts events marked by Person 1 as having primary-source confirmation.

Shock and importance thresholds are initial configuration values, not fitted
calibration. Review them against the project's data and intended use.
