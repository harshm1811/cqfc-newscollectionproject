"""
test_resolver.py - Unit Tests for EquityResolver (Person A)
"""

import pytest
from equity.resolver import EquityResolver


def test_resolver_init():
    resolver = EquityResolver()
    assert resolver is not None
    assert len(resolver.equities_by_symbol) > 0


def test_resolve_exact_ticker():
    resolver = EquityResolver()
    profile = resolver.resolve("RELIANCE")
    assert profile is not None
    assert profile.ticker == "RELIANCE"
    assert "Reliance Industries Limited" in profile.company_name
    assert "Jio Platforms" in profile.important_businesses


def test_resolve_case_insensitive_symbol():
    resolver = EquityResolver()
    profile = resolver.resolve("infy")
    assert profile is not None
    assert profile.ticker == "INFY"


def test_resolve_alias():
    resolver = EquityResolver()
    profile = resolver.resolve("RIL")
    assert profile is not None
    assert profile.ticker == "RELIANCE"


def test_resolve_fuzzy_name():
    resolver = EquityResolver()
    profile = resolver.resolve("tata motors")
    assert profile is not None
    assert profile.ticker == "TATAMOTORS"
