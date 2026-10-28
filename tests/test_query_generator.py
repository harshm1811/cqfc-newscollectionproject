"""
test_query_generator.py - Unit Tests for QueryGenerator (Person A)
"""

import pytest
from equity.query_generator import QueryGenerator


def test_query_generator_init():
    qgen = QueryGenerator()
    assert qgen is not None
    assert len(qgen.templates) > 0


def test_generate_categories(sample_reliance_profile):
    qgen = QueryGenerator()
    queries = qgen.generate(sample_reliance_profile)
    assert "earnings" in queries
    assert "merger_acquisition" in queries
    assert any("Jio Platforms" in q for q in queries.get("subsidiaries", []))


def test_flat_query_list(sample_reliance_profile):
    qgen = QueryGenerator()
    flat = qgen.get_flat_query_list(sample_reliance_profile)
    assert len(flat) > 10
    # Ensure all items in flat list are unique
    assert len(flat) == len(set(flat))
