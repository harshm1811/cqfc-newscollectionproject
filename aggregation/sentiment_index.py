"""Event-level weighted sentiment calculations.

An event contributes once regardless of how many articles cover it. The
weighted ticker/date score is a normalized weighted mean (sum(w*s)/sum(w));
it is not the unbounded sum of contributions. Weights are the product of
relevance, importance, source quality and time weight.
"""

import numpy as np
import pandas as pd


def event_contributions(events: pd.DataFrame) -> pd.DataFrame:
    out = events.copy()
    if "sentiment_score" not in out:
        probs = ["positive_probability", "negative_probability"]
        if all(c in out for c in probs):
            out["sentiment_score"] = pd.to_numeric(out[probs[0]], errors="coerce") - pd.to_numeric(out[probs[1]], errors="coerce")
        else:
            out["sentiment_score"] = np.nan
    for c in ("relevance", "importance_score", "source_quality", "time_weight"):
        if c not in out:
            out[c] = np.nan
        out[c] = pd.to_numeric(out[c], errors="coerce").clip(lower=0)
    out["sentiment_score"] = pd.to_numeric(out["sentiment_score"], errors="coerce").clip(-1, 1)
    score_fields = ["relevance", "importance_score", "source_quality", "time_weight"]
    out["score_missing_reason"] = out[score_fields].isna().apply(
        lambda row: ",".join(row.index[row].tolist()), axis=1
    )
    out["weight"] = out[score_fields].prod(axis=1, min_count=len(score_fields))
    out["weight"] = out["weight"].fillna(0.0)
    out["contribution"] = out["sentiment_score"] * out["weight"]
    return out


def aggregate_event_sentiment(events: pd.DataFrame, *, method="weighted_mean") -> pd.DataFrame:
    """Aggregate events by ticker/date; method is weighted_mean, mean, or sum."""
    if method not in {"weighted_mean", "mean", "sum"}:
        raise ValueError("method must be 'weighted_mean', 'mean', or 'sum'")
    e = event_contributions(events)
    if e.empty:
        return pd.DataFrame(columns=["ticker", "date", "MeanSentiment", "WeightedSentiment"])
    time_col = "first_article_at" if "first_article_at" in e else "published_at"
    e["date"] = pd.to_datetime(e[time_col], utc=True, errors="coerce").dt.normalize()
    e = e.dropna(subset=["ticker", "date"])
    g = e.groupby(["ticker", "date"], as_index=False, sort=True)
    result = g.agg(MeanSentiment=("sentiment_score", "mean"), weighted_numerator=("contribution", "sum"), weight_sum=("weight", "sum"))
    if method == "weighted_mean":
        result["WeightedSentiment"] = result.weighted_numerator.div(result.weight_sum.replace(0, np.nan))
    elif method == "mean":
        result["WeightedSentiment"] = result["MeanSentiment"]
    else:
        result["WeightedSentiment"] = result["weighted_numerator"]
    return result.drop(columns=["weighted_numerator", "weight_sum"])
