"""
run_tests.py - Group 1 Verification Test Suite

Covers:
1. Full listed NSE universe resolution (2,600+ companies)
2. Typo, case, and character transposition tolerance ('relaince', 'Relancie', 'Tatamotrs', 'Infsys')
3. Informal acronyms and aliases ('SBI', 'SBI Bank', 'L&T', 'HDFC')
4. Point-in-time timestamp standardizer (UTC ISO-8601, zero date invention)
5. Query generator coverage across financial categories
6. Standard RawArticleRecord schema validation (Group 1 -> Group 2 contract)
"""

import sys
import traceback
from datetime import datetime

from equity.profile import EquityProfile
from equity.resolver import EquityResolver
from equity.query_generator import QueryGenerator
from collectors.base_collector import RawArticleRecord
from utils.timestamp_parser import parse_to_utc_iso, get_current_utc_iso


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


def test_full_universe_loaded():
    resolver = EquityResolver()
    count = len(resolver.equities_by_symbol)
    assert count > 2000, f"Expected >2000 NSE companies, found {count}"
    print(f"✓ test_full_universe_loaded passed ({count} NSE equities active)")


def test_typo_and_transposition_tolerance():
    resolver = EquityResolver()
    
    # Reliance variations with transpositions and case anomalies
    for query in ["Reliance", "reliance", "relaince", "reLaince", "Relancie"]:
        p = resolver.resolve(query)
        assert p is not None, f"Failed for '{query}'"
        assert p.ticker == "RELIANCE", f"Expected RELIANCE for '{query}', got {p.ticker}"

    # Tata Motors typo
    p_tata = resolver.resolve("Tatamotrs")
    assert p_tata is not None and "TATAMOTORS" in p_tata.ticker or "TMCV" in p_tata.ticker

    # Infosys typo
    p_infy = resolver.resolve("Infsys")
    assert p_infy is not None and p_infy.ticker == "INFY"

    print("✓ test_typo_and_transposition_tolerance passed ('relaince', 'Relancie', 'Tatamotrs', 'Infsys')")


def test_acronym_and_informal_resolution():
    resolver = EquityResolver()
    
    # State Bank of India
    p_sbi = resolver.resolve("SBI")
    assert p_sbi is not None and p_sbi.ticker == "SBIN"
    
    p_sbi_bank = resolver.resolve("SBI Bank")
    assert p_sbi_bank is not None and p_sbi_bank.ticker == "SBIN"
    
    # HDFC Bank
    p_hdfc = resolver.resolve("HDFC")
    assert p_hdfc is not None and p_hdfc.ticker == "HDFCBANK"
    
    # Larsen & Toubro
    p_lt = resolver.resolve("L&T")
    assert p_lt is not None and p_lt.ticker == "LT"

    # Other listed stocks
    for name, expected_ticker in [("Wipro", "WIPRO"), ("Zomato", "ZOMATO"), ("Coal India", "COALINDIA")]:
        p = resolver.resolve(name)
        assert p is not None and p.ticker == expected_ticker, f"Expected {expected_ticker} for '{name}'"

    print("✓ test_acronym_and_informal_resolution passed ('SBI', 'SBI Bank', 'L&T', 'HDFC', 'Wipro', 'Zomato')")


def test_timestamp_parser():
    # 1. RFC-822 RSS formats
    iso1 = parse_to_utc_iso("Mon, 27 Oct 2026 14:30:00 GMT")
    assert iso1 == "2026-10-27T14:30:00Z"

    # 2. ISO-8601 strings
    iso2 = parse_to_utc_iso("2026-10-28T09:15:00Z")
    assert iso2 == "2026-10-28T09:15:00Z"

    # 3. Indian exchange timestamp format
    iso3 = parse_to_utc_iso("28-Oct-2026 15:45:00")
    assert iso3 == "2026-10-28T15:45:00Z"

    # 4. CRITICAL RULE: Missing, empty, or unparseable timestamps MUST return None (never invent dates)
    assert parse_to_utc_iso(None) is None
    assert parse_to_utc_iso("") is None
    assert parse_to_utc_iso("null") is None
    assert parse_to_utc_iso("unparseable garbage string") is None

    # 5. Point-in-time capture for first_seen_at / retrieved_at
    now_ts = get_current_utc_iso()
    assert now_ts.endswith("Z") and "T" in now_ts

    print("✓ test_timestamp_parser passed (strictly normalizes to UTC ISO-8601, zero date invention)")


def test_query_generator():
    resolver = EquityResolver()
    profile = resolver.resolve("RELIANCE")
    qgen = QueryGenerator()
    
    categories = qgen.generate(profile)
    assert "earnings" in categories
    assert "merger_acquisition" in categories
    assert "subsidiaries" in categories
    
    flat = qgen.get_flat_query_list(profile)
    assert len(flat) > 10
    assert len(flat) == len(set(flat))  # Deduplicated
    print(f"✓ test_query_generator passed ({len(flat)} unique queries generated across categories)")


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
    print("✓ test_raw_article_record_schema passed (conforms to Group 1 -> Group 2 contract)")


def main():
    print("==================================================")
    print("        EQUITY NEWS INTELLIGENCE - GROUP 1        ")
    print("              SYSTEM VERIFICATION                 ")
    print("==================================================")
    tests = [
        test_equity_profile,
        test_full_universe_loaded,
        test_typo_and_transposition_tolerance,
        test_acronym_and_informal_resolution,
        test_timestamp_parser,
        test_query_generator,
        test_raw_article_record_schema
    ]
    
    passed = 0
    for t in tests:
        try:
            t()
            passed += 1
        except Exception as e:
            print(f"✗ {t.__name__} FAILED: {e}")
            traceback.print_exc()
            
    print("\n--------------------------------------------------")
    print(f"Result: {passed}/{len(tests)} tests passed.")
    if passed == len(tests):
        print("ALL TESTS PASSED WITH 100% SUCCESS!")
    else:
        sys.exit(1)


if __name__ == "__main__":
    main()
