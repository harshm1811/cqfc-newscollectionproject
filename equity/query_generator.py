"""
query_generator.py - Targeted Financial Search Query Generator

Primary Responsibilities:
- Converts canonical EquityProfile into structured, high-signal search queries.
- Covers mandatory financial categories:
    * General
    * Earnings & Quarterly Results
    * Guidance & Outlook
    * M&A (Mergers & Acquisitions)
    * Expansion & CAPEX
    * Debt & Capital Raising
    * Dividends & Buybacks
    * Management Changes
    * Regulation, Litigation & SEBI Orders
    * Products & Contracts
    * Key Subsidiaries / Divisions
"""

from typing import List, Dict, Optional
from .profile import EquityProfile


class QueryGenerator:
    """
    Generates categorical search queries tailored for search engines and RSS feeds.
    """

    def __init__(self, templates_path: Optional[str] = None):
        """
        Initialize with path to query_templates.json.
        """
        # TODO (Person A): Load templates from config/query_templates.json
        pass

    def generate(
        self,
        profile: EquityProfile,
        categories: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Generate search queries for the given equity profile.
        
        Args:
            profile: Canonical EquityProfile
            categories: Optional subset of categories to generate. If None, generates all.
            
        Returns:
            Dictionary mapping category_name -> list of search query strings.
            
        Example output:
            {
                "earnings": [
                    '"Reliance Industries" earnings',
                    '"Reliance Industries" quarterly results'
                ],
                "subsidiaries": [
                    '"Jio Platforms" Reliance Industries',
                    '"Reliance Retail" expansion'
                ]
            }
        """
        # TODO (Person A): Implement query formatting using profile.company_name,
        # profile.ticker, and profile.important_businesses
        raise NotImplementedError("QueryGenerator.generate() to be implemented by Person A")

    def get_flat_query_list(self, profile: EquityProfile) -> List[str]:
        """
        Convenience method returning a deduplicated flat list of all generated queries.
        """
        # TODO (Person A): Return unique list of all formatted search strings
        pass
