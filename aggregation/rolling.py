"""Calendar-day rolling aggregates. Windows include the current date and
prior calendar dates only (right-closed); missing dates are filled with zero
for rolling weighted sentiment and news volume. This avoids future leakage.
"""
import numpy as np
import pandas as pd


def add_rolling_sentiment(daily: pd.DataFrame, windows=(1, 3, 7, 30), *, value_col="WeightedSentiment", fill_missing_dates=True):
    if daily.empty:
        return daily.copy()
    parts = []
    for ticker, group in daily.groupby("ticker", sort=False):
        g = group.copy()
        g["date"] = pd.to_datetime(g["date"], utc=True).dt.normalize()
        g = g.sort_values("date").set_index("date")
        if fill_missing_dates:
            g = g.asfreq("D")
            g["ticker"] = ticker
            g[value_col] = g[value_col].fillna(0.0)
        for n in windows:
            g[f"Sentiment{n}D"] = g[value_col].rolling(f"{int(n)}D", min_periods=1, closed="both").mean()
        g = g.reset_index().rename(columns={"index": "date"})
        parts.append(g)
    return pd.concat(parts, ignore_index=True).sort_values(["ticker", "date"]).reset_index(drop=True)


def add_sentiment_momentum(frame: pd.DataFrame, *, short_col="Sentiment1D", long_col="Sentiment7D", output_col="SentimentMomentum", missing="zero"):
    out = frame.copy()
    short, long = out[short_col], out[long_col]
    if missing == "zero":
        out[output_col] = short.fillna(0) - long.fillna(0)
    elif missing == "propagate":
        out[output_col] = short - long
    else:
        raise ValueError("missing must be 'zero' or 'propagate'")
    return out
