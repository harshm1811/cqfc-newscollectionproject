"""
run_tests.py - Simple, zero-dependency test runner for Group 1
"""

import sys
import traceback
from datetime import datetime

from equity.profile import EquityProfile
from equity.resolver import EquityResolver
from equity.query_generator import QueryGenerator
from collectors.base_collector import RawArticleRecord
from utils.timestamp_parser import parse_to_utc_iso


def test_equity_profile():
    p = EquityProfile(
        company_name="Reliance Industries Limited",
        ticker="RELIANCE",
        exchange="NSE",
        country="India",
        isin="INE002A01018",
        aliases=["Reliance", "RIL"],
        important_businesses=["Jio Platforms", "Reliance Retail"]
    )
    assert p.ticker == "RELIANCE"
    assert "Jio Platforms" in p.important_businesses
    d = p.to_dict()
    assert d["country"] == "India"
    print("✓ test_equity_profile passed")


def test_equity_resolver():
    resolver = EquityResolver()
    
    # 1. Exact Ticker
    p1 = resolver.resolve("RELIANCE")
    assert p1 is not None and p1.ticker == "RELIANCE"
    
    # 2. Case insensitive
    p2 = resolver.resolve("infy")
    assert p2 is not None and p2.ticker == "INFY"
    
    # 3. Known Alias
    p3 = resolver.resolve("RIL")
    assert p3 is not None and p3.ticker == "RELIANCE"
    
    # 4. Fuzzy Name match
    p4 = resolver.resolve("tata motors")
    assert p4 is not None and p4.ticker == "TATAMOTORS"
    
    print("✓ test_equity_resolver passed")


def test_query_generator():
    resolver = EquityResolver()
    profile = resolver.resolve("RELIANCE")
    qgen = QueryGenerator()
    
    categories = qgen.generate(profile)
    assert "earnings" in categories
    assert "merger_acquisition" in categories
    
    flat = qgen.get_flat_query_list(profile)
    assert len(flat) > 10
    assert len(flat) == len(set(flat))  # Deduplicated
    print(f"✓ test_query_generator passed ({len(flat)} unique queries generated)")


def test_raw_article_record_schema():
    record = RawArticleRecord(
        company_name="Reliance Industries Limited",
        ticker="RELIANCE",
        title="Test Headline",
        description="Test Description",
        url="https://example.com/article",
        source="Test Source",
        source_type="NEWS_RSS",
        primary_source=False,
        published_at="2026-10-28T10:00:00Z",
        first_seen_at="2026-10-28T10:05:00Z",
        retrieved_at="2026-10-28T10:05:00Z",
        collector="TestCollector"
    )
    assert record.ticker == "RELIANCE"
    assert record.primary_source is False
    assert record.source_type == "NEWS_RSS"
    print("✓ test_raw_article_record_schema passed")


def test_timestamp_parser():
    iso1 = parse_to_utc_iso("Mon, 27 Oct 2026 14:30:00 GMT")
    assert iso1 == "2026-10-27T14:30:00Z"
    
    # Missing or unparseable timestamps must remain None (never invent dates)
    assert parse_to_utc_iso(None) is None
    assert parse_to_utc_iso("") is None
    assert parse_to_utc_iso("not a date") is None
    print("✓ test_timestamp_parser passed (strictly preserves None for invalid dates)")


def main():
    print("=== RUNNING GROUP 1 TEST SUITE ===")
    tests = [
        test_equity_profile,
        test_equity_resolver,
        test_query_generator,
        test_raw_article_record_schema,
        test_timestamp_parser
    ]
    
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__} FAILED: {e}")
            traceback.print_exc()
            
    print(f"\nResult: {passed}/{len(tests)} tests passed.")
    if passed == len(tests):
        print("ALL TESTS PASSED SUCCESSFULLY!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
