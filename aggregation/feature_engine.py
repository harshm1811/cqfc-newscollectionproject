"""Daily equity feature dataset built from article and event tables."""
from dataclasses import dataclass
import numpy as np
import pandas as pd

from .rolling import add_rolling_sentiment, add_sentiment_momentum
from .sentiment_index import aggregate_event_sentiment, event_contributions


@dataclass
class FeatureConfig:
    rolling_windows: tuple[int, ...] = (1, 3, 7, 30)
    aggregation_method: str = "weighted_mean"
    volume_lookback: int = 30
    volume_z_threshold: float = 2.0
    positive_shock_threshold: float = 0.5
    negative_shock_threshold: float = -0.5
    high_importance_threshold: float = 0.75
    momentum_short_window: int = 1
    momentum_long_window: int = 7
    momentum_missing: str = "zero"


def _day(series):
    return pd.to_datetime(series, utc=True, errors="coerce").dt.normalize()


def build_feature_dataset(articles: pd.DataFrame, events: pd.DataFrame, mappings: pd.DataFrame | None = None, *, config=None) -> pd.DataFrame:
    """Build ticker/day feature rows. Article metrics come from articles;
    event metrics are computed once per unique event. All thresholds/windows
    are configurable via FeatureConfig.
    """
    cfg = config or FeatureConfig()
    a, e = articles.copy(), events.copy()
    if a.empty and e.empty:
        return pd.DataFrame()
    if not a.empty:
        a["date"] = _day(a["published_at"] if "published_at" in a else a["first_seen_at"])
        a = a.dropna(subset=["ticker", "date"])
        if "relevance" not in a: a["relevance"] = 1.0
        a["relevance"] = pd.to_numeric(a["relevance"], errors="coerce").fillna(1)
        articles_daily = a.groupby(["ticker", "date"], as_index=False).agg(NewsCount=("article_id", "nunique"), RelevantArticleCount=("relevance", lambda x: int((x > 0).sum())))
    else:
        articles_daily = pd.DataFrame(columns=["ticker", "date", "NewsCount", "RelevantArticleCount"])
    ev = event_contributions(e)
    if not ev.empty:
        time_col = "first_article_at" if "first_article_at" in ev else "published_at"
        ev["date"] = _day(ev[time_col])
        ev = ev.dropna(subset=["ticker", "date"]).drop_duplicates("event_id" if "event_id" in ev else ["ticker", "date", "title"])
        ev["PositiveEventCount"] = (ev.sentiment_score > 0).astype(int)
        ev["NegativeEventCount"] = (ev.sentiment_score < 0).astype(int)
        ev["NeutralEventCount"] = (ev.sentiment_score == 0).astype(int)
        ev["PositiveShock"] = (ev.sentiment_score >= cfg.positive_shock_threshold).astype(int)
        ev["NegativeShock"] = (ev.sentiment_score <= cfg.negative_shock_threshold).astype(int)
        ev["HighImportancePositiveEvent"] = ((ev.importance_score >= cfg.high_importance_threshold) & (ev.sentiment_score > 0)).astype(int)
        ev["HighImportanceNegativeEvent"] = ((ev.importance_score >= cfg.high_importance_threshold) & (ev.sentiment_score < 0)).astype(int)
        if "primary_source_confirmed" not in ev: ev["primary_source_confirmed"] = False
        ev["primary_source_confirmed"] = ev.primary_source_confirmed.fillna(False).astype(bool)
        numeric = ["importance_score"]
        metrics = ["event_id", "PositiveEventCount", "NegativeEventCount", "NeutralEventCount", "PositiveShock", "NegativeShock", "HighImportancePositiveEvent", "HighImportanceNegativeEvent", "primary_source_confirmed"]
        event_daily = ev.groupby(["ticker", "date"], as_index=False).agg(UniqueEventCount=("event_id", "nunique") if "event_id" in ev else ("sentiment_score", "size"), PositiveEventCount=("PositiveEventCount", "sum"), NegativeEventCount=("NegativeEventCount", "sum"), NeutralEventCount=("NeutralEventCount", "sum"), PositiveShock=("PositiveShock", "sum"), NegativeShock=("NegativeShock", "sum"), HighImportancePositiveEvent=("HighImportancePositiveEvent", "sum"), HighImportanceNegativeEvent=("HighImportanceNegativeEvent", "sum"), MeanImportance=("importance_score", "mean"), MaxImportance=("importance_score", "max"), PrimarySourceEventCount=("primary_source_confirmed", "sum"))
        sent_daily = aggregate_event_sentiment(ev, method=cfg.aggregation_method)
        event_daily = event_daily.merge(sent_daily, on=["ticker", "date"], how="left")
        event_daily["NewsVolume"] = event_daily["UniqueEventCount"]
        # Sample standard deviation of prior calendar observations; current day excluded.
        event_daily = event_daily.sort_values(["ticker", "date"])
        event_daily["NewsVolumeZScore"] = event_daily.groupby("ticker")["NewsVolume"].transform(lambda s: (s - s.shift(1).rolling(cfg.volume_lookback, min_periods=2).mean()) / s.shift(1).rolling(cfg.volume_lookback, min_periods=2).std().replace(0, np.nan))
        # SourceAgreement = 1 - population SD of unique article source sentiment
        # per event, averaged over events; syndicated copies under one source count once.
        if not a.empty and mappings is not None and not mappings.empty:
            src = mappings.merge(a, on="article_id", how="left", suffixes=("", "_article"))
            src["source_key"] = src.get("source", pd.Series(index=src.index, dtype=object)).fillna("").astype(str).str.casefold().str.strip()
            src["article_score"] = pd.to_numeric(src.get("sentiment_score", np.nan), errors="coerce")
            if src["article_score"].isna().all():
                pos = pd.to_numeric(src.get("positive_probability", np.nan), errors="coerce")
                neg = pd.to_numeric(src.get("negative_probability", np.nan), errors="coerce")
                src["article_score"] = pos - neg
            src = src.dropna(subset=["article_score"]).drop_duplicates(["event_id", "source_key"])
            agree = src.groupby(["event_id", "ticker"], as_index=False).article_score.std(ddof=0).rename(columns={"article_score": "sd"})
            agree["agreement"] = (1 - agree.sd).clip(0, 1)
            event_dates = ev[["event_id", "ticker", "date"]].drop_duplicates()
            agree = agree.merge(event_dates, on=["event_id", "ticker"], how="left")
            event_agree = agree.groupby(["ticker", "date"], as_index=False).agreement.mean().rename(columns={"agreement": "SourceAgreement"})
            event_daily = event_daily.merge(event_agree, on=["ticker", "date"], how="left")
        else:
            event_daily["SourceAgreement"] = np.nan
        dispersion = ev.groupby(["ticker", "date"], as_index=False).sentiment_score.std(ddof=0).rename(columns={"sentiment_score": "SentimentDispersion"})
        event_daily = event_daily.merge(dispersion, on=["ticker", "date"], how="left")
    else:
        event_daily = pd.DataFrame(columns=["ticker", "date"])
    daily = articles_daily.merge(event_daily, on=["ticker", "date"], how="outer")
    for c in ("NewsCount", "RelevantArticleCount", "UniqueEventCount", "PositiveEventCount", "NegativeEventCount", "NeutralEventCount", "NewsVolume", "PositiveShock", "NegativeShock", "HighImportancePositiveEvent", "HighImportanceNegativeEvent", "PrimarySourceEventCount"):
        if c in daily: daily[c] = daily[c].fillna(0).astype(int)
    if "ticker" in daily:
        daily = add_rolling_sentiment(daily, windows=cfg.rolling_windows, fill_missing_dates=True)
        short, long = f"Sentiment{cfg.momentum_short_window}D", f"Sentiment{cfg.momentum_long_window}D"
        if short in daily and long in daily:
            daily = add_sentiment_momentum(daily, short_col=short, long_col=long, missing=cfg.momentum_missing)
    return daily.sort_values(["ticker", "date"]).reset_index(drop=True)
