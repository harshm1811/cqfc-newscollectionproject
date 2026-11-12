"""
run_demo.py - Interactive Test Runner for Group 3 Pipeline.

Usage:
    python run_demo.py
    python run_demo.py --input path/to/your_articles.json
"""

import argparse
import json
import os
import sys
from datetime import datetime, timezone
import pandas as pd

from group3_pipeline import run_group3_pipeline


def print_banner(text: str, char="="):
    print("\n" + char * 80)
    print(f" {text}")
    print(char * 80)


def main():
    parser = argparse.ArgumentParser(description="Test runner for Group 3 Event & Sentiment Engine")
    parser.add_argument(
        "--input",
        type=str,
        default="data/mock/mock_group2_articles.json",
        help="Path to mock clean articles JSON file from Group 2",
    )
    parser.add_argument(
        "--outdir",
        type=str,
        default="data/output",
        help="Directory to save generated event and daily feature datasets",
    )
    args = parser.parse_args()

    input_path = args.input
    if not os.path.exists(input_path):
        print(f"Error: Input file not found at {input_path}")
        sys.exit(1)

    with open(input_path, "r", encoding="utf-8") as f:
        raw_articles = json.load(f)

    print_banner(f"GROUP 3 ENGINE: INGESTING {len(raw_articles)} ARTICLES FROM GROUP 2")
    tickers = sorted(list({a.get("ticker", "UNKNOWN") for a in raw_articles}))
    print(f"Tickers found: {', '.join(tickers)}")
    print(f"Source file:   {input_path}")

    # Run Group 3 Pipeline
    as_of = datetime(2025, 10, 23, 12, 0, 0, tzinfo=timezone.utc)
    print("\nExecuting Pipeline (Sentiment -> Clustering -> Classification -> Scoring -> Feature Engine)...")
    result = run_group3_pipeline(raw_articles, as_of=as_of, to_snake_case=True)
    print(f"Sentiment model: {result.sentiment_model_name}")
    if result.sentiment_fallback_reason:
        print(f"Fallback reason: {result.sentiment_fallback_reason}")

    # 1. Display Clustered Financial Events
    print_banner("1. DISCOVERED FINANCIAL EVENTS (GROUP 3 -> GROUP 4 EVENT DATASET)")
    events_summary = []
    for ev in result.events:
        rec = ev.to_group4_record()
        events_summary.append({
            "Event ID": rec["event_id"],
            "Ticker": rec["ticker"],
            "Type": rec["event_type"],
            "Sentiment": f"{rec['sentiment_score']:+.2f}",
            "Importance": f"{rec['importance_score']:.2f}",
            "Articles": rec["article_count"],
            "Primary?": "YES" if rec["primary_source_present"] else "NO",
            "Headline": rec["headline"][:45] + ("..." if len(rec["headline"]) > 45 else ""),
        })

    events_table = pd.DataFrame(events_summary)
    print(events_table.to_string(index=False))

    # 2. Display Daily Feature Dataset
    print_banner("2. DAILY QUANTITATIVE FEATURES (GROUP 3 -> GROUP 4 DAILY FEATURES)")
    feature_cols_to_show = [
        "date",
        "ticker",
        "news_count",
        "unique_event_count",
        "weighted_sentiment",
        "sentiment_1d",
        "sentiment_7d",
        "sentiment_momentum",
        "news_volume_zscore",
        "positive_shock",
        "negative_shock",
    ]
    df_show = result.daily_features.copy()
    available_cols = [c for c in feature_cols_to_show if c in df_show.columns]

    # Format floating point numbers for clean terminal display
    for col in ["weighted_sentiment", "sentiment_1d", "sentiment_7d", "sentiment_momentum", "news_volume_zscore"]:
        if col in df_show:
            df_show[col] = df_show[col].apply(lambda x: f"{x:+.2f}" if pd.notna(x) else "  -  ")

    print(df_show[available_cols].to_string(index=False))

    # 3. Export Datasets for Group 4
    os.makedirs(args.outdir, exist_ok=True)
    events_export_path = os.path.join(args.outdir, "events.json")
    features_export_path = os.path.join(args.outdir, "daily_features.csv")

    with open(events_export_path, "w", encoding="utf-8") as f:
        json.dump(result.event_records, f, indent=2)

    result.daily_features.to_csv(features_export_path, index=False)

    print_banner("3. EXPORT COMPLETE (READY FOR GROUP 4)")
    print(f"Events Dataset saved to:       {events_export_path}")
    print(f"Daily Features CSV saved to:   {features_export_path}")
    print("=" * 80 + "\n")


if __name__ == "__main__":
    main()
