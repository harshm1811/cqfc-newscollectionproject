"""
resolver.py - Equity Resolver Engine

Primary Responsibilities:
1. Accept raw user queries: e.g., 'Reliance', 'RIL', 'tata motor', 'INFY'.
2. Resolve to canonical EquityProfile using:
   - Exact ticker match
   - Exact alias match
   - Fuzzy name matching against offline NSE listed companies master list
3. Flag ambiguous queries (e.g., 'Tata' could be Tata Motors, Tata Steel, Tata Power).
4. Cache resolved profiles locally in SQLite to prevent redundant lookups.
"""

from typing import Optional, List, Dict, Any
from pathlib import Path
from .profile import EquityProfile


class EquityResolver:
    """
    Resolves noisy user company inputs into canonical EquityProfile objects.
    """

    def __init__(
        self,
        seed_csv_path: Optional[str] = None,
        aliases_json_path: Optional[str] = None,
        cache_db_path: Optional[str] = None
    ):
        """
        Initialize the resolver with master data paths.
        
        Args:
            seed_csv_path: Path to nse_listed_companies.csv
            aliases_json_path: Path to equity_aliases_seed.json
            cache_db_path: Path to SQLite cache database
        """
        # TODO (Person A):
        # 1. Load seed CSV (SYMBOL, NAME OF COMPANY, ISIN) into memory (e.g., pandas or dict)
        # 2. Load alias mappings into memory
        # 3. Initialize SQLite cache connection
        pass

    def resolve(self, query: str, threshold: float = 80.0) -> Optional[EquityProfile]:
        """
        Main resolution method.
        
        Step-by-step resolution strategy:
        1. Clean/strip query, check local SQLite cache first.
        2. Exact ticker lookup (case-insensitive).
        3. Check alias seed map (e.g., 'RIL' -> 'RELIANCE').
        4. Fuzzy match against master company names using rapidfuzz / thefuzz.
        5. Check for ambiguity: if top 2 matches have very close scores, handle accordingly.
        6. Store result in SQLite cache and return EquityProfile.
        
        Args:
            query: Raw company string entered by user
            threshold: Fuzzy matching cutoff score (0-100)
            
        Returns:
            EquityProfile or None if no confident match is found.
        """
        # TODO (Person A): Implement resolution logic
        raise NotImplementedError("EquityResolver.resolve() to be implemented by Person A")

    def handle_ambiguity(self, query: str, candidates: List[Dict[str, Any]]) -> Optional[EquityProfile]:
        """
        Handle ambiguous user queries by ranking candidates or returning None with warnings.
        """
        # TODO (Person A): Implement ambiguity detection
        pass
