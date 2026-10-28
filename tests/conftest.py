"""
conftest.py - Pytest Fixtures and Mock Data for Group 1 Tests
"""

import pytest
from datetime import datetime
from equity.profile import EquityProfile


@pytest.fixture
def sample_reliance_profile():
    return EquityProfile(
        company_name="Reliance Industries Limited",
        ticker="RELIANCE",
        exchange="NSE",
        country="India",
        isin="INE002A01018",
        aliases=["Reliance Industries", "RIL", "Reliance"],
        important_businesses=["Jio Platforms", "Reliance Retail"]
    )


@pytest.fixture
def sample_tcs_profile():
    return EquityProfile(
        company_name="Tata Consultancy Services Limited",
        ticker="TCS",
        exchange="NSE",
        country="India",
        isin="INE467B01029",
        aliases=["Tata Consultancy Services", "TCS"],
        important_businesses=["TCS BaNCS"]
    )
