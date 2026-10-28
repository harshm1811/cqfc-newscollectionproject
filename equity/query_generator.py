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

from typing import List, Dict, Optional, Any
import json
from pathlib import Path
from .profile import EquityProfile


class QueryGenerator:
    """
    Generates categorical search queries tailored for search engines and RSS feeds.
    """

    def __init__(self, templates_path: Optional[str] = None):
        base_dir = Path(__file__).resolve().parent.parent
        self.templates_path = Path(templates_path) if templates_path else base_dir / "config" / "query_templates.json"
        self.templates: Dict[str, List[str]] = self._load_templates()

    def _load_templates(self) -> Dict[str, List[str]]:
        if self.templates_path.exists():
            try:
                with open(self.templates_path, mode="r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        # Fallback default templates
        return {
            "general": ["\"{company_name}\"", "\"{ticker}\""],
            "earnings": ["\"{company_name}\" earnings", "\"{company_name}\" quarterly results"],
            "guidance": ["\"{company_name}\" revenue guidance", "\"{company_name}\" outlook"],
            "merger_acquisition": ["\"{company_name}\" acquisition", "\"{company_name}\" merger"],
            "expansion_capex": ["\"{company_name}\" expansion", "\"{company_name}\" capex"],
            "debt_financing": ["\"{company_name}\" debt", "\"{company_name}\" fundraising"],
            "corporate_actions": ["\"{company_name}\" dividend", "\"{company_name}\" share buyback"],
            "management": ["\"{company_name}\" CEO appointment OR resignation"],
            "regulation_litigation": ["\"{company_name}\" SEBI", "\"{company_name}\" litigation"],
            "products_contracts": ["\"{company_name}\" new contract"],
            "subsidiaries": ["\"{subsidiary}\" \"{company_name}\""]
        }

    def generate(
        self,
        profile: EquityProfile,
        categories: Optional[List[str]] = None
    ) -> Dict[str, List[str]]:
        """
        Generate search queries for the given equity profile.
        """
        result: Dict[str, List[str]] = {}
        target_categories = categories or list(self.templates.keys())

        # Clean primary name for query readability (e.g. 'Reliance Industries Limited' -> 'Reliance Industries')
        clean_name = profile.company_name
        for suffix in [" Limited", " Ltd.", " Ltd"]:
            if clean_name.endswith(suffix):
                clean_name = clean_name[:-len(suffix)]

        for cat in target_categories:
            patterns = self.templates.get(cat, [])
            cat_queries: List[str] = []

            for pattern in patterns:
                if "{subsidiary}" in pattern:
                    for sub in profile.important_businesses:
                        formatted = pattern.replace("{subsidiary}", sub)
                        formatted = formatted.replace("{company_name}", clean_name)
                        formatted = formatted.replace("{ticker}", profile.ticker)
                        cat_queries.append(formatted)
                else:
                    formatted = pattern.replace("{company_name}", clean_name)
                    formatted = formatted.replace("{ticker}", profile.ticker)
                    cat_queries.append(formatted)

            if cat_queries:
                result[cat] = cat_queries

        return result

    def get_flat_query_list(self, profile: EquityProfile) -> List[str]:
        """
        Convenience method returning a deduplicated flat list of all generated queries.
        """
        grouped = self.generate(profile)
        seen = set()
        flat_list = []
        for cat_queries in grouped.values():
            for q in cat_queries:
                if q not in seen:
                    seen.add(q)
                    flat_list.append(q)
        return flat_list
