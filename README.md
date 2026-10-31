# Equity News Quant Feature Engineering

Standalone Group 3 Person 3 feature pipeline. It consumes the article, event,
and article/event mapping lists emitted by Person 1, without defining or
modifying Person 1's models. Pandas and NumPy are required.

## Use

```python
from feature_engineering.adapters import adapt_enriched_outputs
from feature_engineering import FeatureConfig, build_feature_dataset

articles, events, mappings = build_enriched_events(...)
article_df, event_df, mapping_df = adapt_enriched_outputs(articles, events, mappings)
daily = build_feature_dataset(
    article_df, event_df, mapping_df,
    config=FeatureConfig(volume_lookback=30),
)
```

`adapt_enriched_outputs` calls `to_dict()` on upstream model objects, retains
IDs and supplied mappings, converts timestamps to UTC, extracts nested
article sentiment, and provides visibly marked mock Person 2 fields when
missing. Supply `person2_by_event={event_id: {"importance_score": ...,
"source_quality": ..., "time_weight": ...}}` and
`relevance_by_article={article_id: score}` to connect real outputs. Mock
defaults are clearly configurable in `InputAdapterConfig`.

## Definitions

- Event contribution: `sentiment × relevance × importance × source quality ×
  time weight`. `WeightedSentiment` is the sum of contributions divided by
  the sum of nonnegative product weights (a normalized weighted mean); zero
  total weight yields missing. `MeanSentiment` is the unweighted event mean.
- Each unique event contributes once to event sentiment/count features;
  article IDs are independently counted for `NewsCount` and
  `RelevantArticleCount`.
- `Sentiment1D/3D/7D/30D` are trailing calendar-day averages including the
  current day. Missing calendar dates are included as zero sentiment. Each
  ticker is processed independently and dates are sorted, so no future data
  enters a feature.
- `SentimentMomentum` is configurable short-window minus long-window
  sentiment; the default is 1D minus 7D. Missing values default to zero.
- `NewsVolume` is unique events per ticker/day. `NewsVolumeZScore` compares
  the current volume with the preceding `volume_lookback` observed daily rows
  (current row excluded), using sample standard deviation; fewer than two
  historical values or zero deviation yields missing.
- Positive/negative/neutral event counts use sentiment sign. Shock flags use
  configurable sentiment cutoffs. High-importance flags combine the
  configured importance cutoff with sentiment sign.
- `MeanImportance` and `MaxImportance` summarize event importance per day.
  `SourceAgreement` is 1 minus the population standard deviation of article
  sentiment scores across distinct source labels for each event, clipped to
  [0, 1], then averaged per ticker/day. Duplicate articles from the same
  source label count once. `SentimentDispersion` is population standard
  deviation of unique event sentiment that day. `PrimarySourceEventCount`
  counts distinct events where Person 1 marks primary source confirmation.

Shock and importance cutoffs are exposed on `FeatureConfig`; adjust them to
the project's calibration rather than treating defaults as fitted values.

Run the unit suite with `python -m unittest discover -s tests -v`.
