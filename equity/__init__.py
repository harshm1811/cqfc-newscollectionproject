"""
equity package initialization.
Provides EquityProfile data model, EquityResolver, and QueryGenerator.
"""

from .profile import EquityProfile
from .resolver import EquityResolver
from .query_generator import QueryGenerator

__all__ = ["EquityProfile", "EquityResolver", "QueryGenerator"]
