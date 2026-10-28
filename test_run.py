"""
test_run.py - Interactive CLI to test any company in Group 1
Usage:
    python test_run.py "Tata Motors"
    python test_run.py "INFY"
    python test_run.py "HDFC Bank"
"""

import sys
import json
from pipeline import collect_equity_news


def main():
    if len(sys.argv) > 1:
        company_query = " ".join(sys.argv[1:])
    else:
        company_query = input("Enter company name or ticker (e.g. TCS, Tata Motors, INFY, ITC): ").strip()

    if not company_query:
        print("Error: No company specified.")
        return

    print(f"\n[1/3] Running Group 1 Pipeline for: '{company_query}'...")
    result = collect_equity_news(company_query)

    print("\n" + "=" * 50)
    print("           GROUP 1 PIPELINE RESULTS")
    print("=" * 50)

    profile = result.get("equity_profile")
    if not profile:
        print(f"❌ Failed to resolve company: {result.get('message')}")
        return

    print(f"✓ Company Name : {profile.get('company_name')}")
    print(f"✓ Ticker       : {profile.get('ticker')}")
    print(f"✓ Exchange     : {profile.get('exchange')} ({profile.get('country')})")
    print(f"✓ Aliases      : {', '.join(profile.get('aliases', []))}")
    if profile.get("important_businesses"):
        print(f"✓ Subsidiaries : {', '.join(profile.get('important_businesses'))}")

    print("\n--- Collector Breakdown ---")
    stats = result.get("collector_stats", {})
    for collector_name, count in stats.items():
        print(f"  • {collector_name:20s}: {count} items discovered")

    print(f"\nTotal Discovered Articles: {result.get('total_articles', 0)}")
    print(f"Status                  : {result.get('status')}")

    # Display sample article if found
    articles = result.get("raw_articles", [])
    if articles:
        print("\n--- Sample Discovered Article (First Item) ---")
        sample = articles[0]
        print(f"Title        : {sample.get('title')}")
        print(f"Source       : {sample.get('source')} ({sample.get('source_type')})")
        print(f"URL          : {sample.get('url')}")
        print(f"Published At : {sample.get('published_at')}")
        print(f"Primary Src  : {sample.get('primary_source')}")
    else:
        print("\n(Note: No live articles returned. If running offline/without internet, collectors degrade gracefully).")

    print("\nRaw data preserved at: data/raw/" + profile.get("ticker") + "/")
    print("=" * 50)


if __name__ == "__main__":
    main()
