"""
test_resolver.py - Unit Tests for EquityResolver (Person A)

Test coverage goals:
1. Exact ticker lookup ('RELIANCE' -> RELIANCE)
2. Case-insensitive lookup ('infy' -> INFY)
3. Alias mapping ('RIL' -> RELIANCE, 'TaMo' -> TATAMOTORS)
4. Fuzzy matching ('reliance ind' -> RELIANCE)
5. Ambiguity handling ('Tata' returns candidates or asks for clarification)
6. Offline execution: all tests must run without external API calls.
"""

import pytest
from equity.resolver import EquityResolver


def test_resolver_init():
    resolver = EquityResolver()
    assert resolver is not None


@pytest.mark.skip(reason="To be implemented once Person A completes resolver logic")
def test_resolve_exact_ticker(sample_reliance_profile):
    resolver = EquityResolver()
    profile = resolver.resolve("RELIANCE")
    assert profile is not None
    assert profile.ticker == "RELIANCE"
    assert "Jio Platforms" in profile.important_businesses
