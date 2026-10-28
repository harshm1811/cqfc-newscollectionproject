"""
test_query_generator.py - Unit Tests for QueryGenerator (Person A)

Test coverage goals:
1. Verify queries generated for all mandatory financial categories:
   - Earnings, Guidance, M&A, CAPEX, Buyback, Litigation, Management, Subsidiaries.
2. Verify formatting contains company name and key subsidiaries.
3. Verify deduplication in flat query list.
"""

import pytest
from equity.query_generator import QueryGenerator


def test_query_generator_init():
    qgen = QueryGenerator()
    assert qgen is not None


@pytest.mark.skip(reason="To be implemented once Person A completes query generator logic")
def test_generate_categories(sample_reliance_profile):
    qgen = QueryGenerator()
    queries = qgen.generate(sample_reliance_profile)
    assert "earnings" in queries
    assert "merger_acquisition" in queries
    assert any("Jio Platforms" in q for q in queries.get("subsidiaries", []))
