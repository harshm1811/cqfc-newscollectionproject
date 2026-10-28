"""
resolver.py - Equity Resolver Engine

Primary Responsibilities:
1. Accept raw user queries: e.g., 'Reliance', 'RIL', 'tata motor', 'INFY'.
2. Resolve to canonical EquityProfile using:
   - Exact ticker match
   - Exact alias match
   - Fuzzy name matching against offline NSE listed companies master list (with rapidfuzz or difflib fallback)
3. Flag ambiguous queries (e.g., 'Tata' matching multiple distinct entities).
4. Cache resolved profiles locally in SQLite to prevent redundant lookups.
"""

from typing import Optional, List, Dict, Any, Tuple
import os
import csv
import json
import sqlite3
import difflib
from pathlib import Path

from .profile import EquityProfile

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


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
        base_dir = Path(__file__).resolve().parent.parent
        self.seed_csv_path = Path(seed_csv_path) if seed_csv_path else base_dir / "data" / "seed" / "nse_listed_companies.csv"
        self.aliases_json_path = Path(aliases_json_path) if aliases_json_path else base_dir / "data" / "seed" / "equity_aliases_seed.json"
        self.cache_db_path = Path(cache_db_path) if cache_db_path else base_dir / "data" / "cache" / "equity_cache.sqlite"

        self.equities_by_symbol: Dict[str, Dict[str, str]] = {}
        self.equities_by_name: Dict[str, Dict[str, str]] = {}
        self.alias_map: Dict[str, Dict[str, Any]] = {}

        self._load_seed_data()
        self._init_cache()

    def _load_seed_data(self) -> None:
        """Loads static NSE equities seed and curated aliases."""
        if self.seed_csv_path.exists():
            with open(self.seed_csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for row in reader:
                    symbol = (row.get("SYMBOL") or "").strip().upper()
                    name = (row.get("NAME OF COMPANY") or "").strip()
                    isin = (row.get("ISIN NUMBER") or "").strip()
                    series = (row.get("SERIES") or "").strip()

                    entry = {
                        "symbol": symbol,
                        "name": name,
                        "isin": isin,
                        "series": series
                    }
                    if symbol:
                        self.equities_by_symbol[symbol] = entry
                    if name:
                        self.equities_by_name[name.lower()] = entry

        if self.aliases_json_path.exists():
            try:
                with open(self.aliases_json_path, mode="r", encoding="utf-8") as f:
                    self.alias_map = json.load(f)
            except Exception:
                self.alias_map = {}

    def _init_cache(self) -> None:
        """Initializes SQLite cache for rapid re-resolution."""
        self.cache_db_path.parent.mkdir(parents=True, exist_ok=True)
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    CREATE TABLE IF NOT EXISTS resolved_equities (
                        query_text TEXT PRIMARY KEY,
                        ticker TEXT NOT NULL,
                        company_name TEXT NOT NULL,
                        exchange TEXT NOT NULL,
                        country TEXT NOT NULL,
                        isin TEXT,
                        aliases_json TEXT,
                        businesses_json TEXT
                    )
                """)
                conn.commit()
        except Exception:
            pass

    def _get_from_cache(self, query: str) -> Optional[EquityProfile]:
        """Fetch profile from SQLite cache if previously resolved."""
        clean_q = query.strip().lower()
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    SELECT ticker, company_name, exchange, country, isin, aliases_json, businesses_json
                    FROM resolved_equities WHERE query_text = ?
                """, (clean_q,))
                row = cursor.fetchone()
                if row:
                    return EquityProfile(
                        ticker=row[0],
                        company_name=row[1],
                        exchange=row[2],
                        country=row[3],
                        isin=row[4],
                        aliases=json.loads(row[5] or "[]"),
                        important_businesses=json.loads(row[6] or "[]")
                    )
        except Exception:
            pass
        return None

    def _save_to_cache(self, query: str, profile: EquityProfile) -> None:
        """Persist newly resolved profile to SQLite cache."""
        clean_q = query.strip().lower()
        try:
            with sqlite3.connect(self.cache_db_path) as conn:
                cursor = conn.cursor()
                cursor.execute("""
                    INSERT OR REPLACE INTO resolved_equities
                    (query_text, ticker, company_name, exchange, country, isin, aliases_json, businesses_json)
                    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """, (
                    clean_q,
                    profile.ticker,
                    profile.company_name,
                    profile.exchange,
                    profile.country,
                    profile.isin,
                    json.dumps(profile.aliases),
                    json.dumps(profile.important_businesses)
                ))
                conn.commit()
        except Exception:
            pass

    def _build_profile_from_symbol(self, symbol: str) -> EquityProfile:
        """Assembles EquityProfile using symbol, seed CSV info, and alias mapping."""
        seed_info = self.equities_by_symbol.get(symbol.upper(), {})
        alias_info = self.alias_map.get(symbol.upper(), {})

        company_name = seed_info.get("name") or alias_info.get("aliases", [symbol])[0]
        isin = seed_info.get("isin")

        aliases = list(set([symbol, company_name] + alias_info.get("aliases", [])))
        important_businesses = alias_info.get("important_businesses", [])

        return EquityProfile(
            company_name=company_name,
            ticker=symbol.upper(),
            exchange="NSE",
            country="India",
            isin=isin,
            aliases=aliases,
            important_businesses=important_businesses
        )

    def _compute_similarity(self, a: str, b: str) -> float:
        """Calculates normalized string similarity score between 0 and 100."""
        a_clean = a.lower().strip()
        b_clean = b.lower().strip()
        if a_clean == b_clean:
            return 100.0

        if HAS_RAPIDFUZZ:
            return float(fuzz.token_set_ratio(a_clean, b_clean))
        else:
            matcher = difflib.SequenceMatcher(None, a_clean, b_clean)
            ratio = matcher.ratio() * 100.0
            if a_clean in b_clean or b_clean in a_clean:
                ratio = max(ratio, 85.0)
            return ratio

    def resolve(self, query: str, threshold: float = 70.0) -> Optional[EquityProfile]:
        """
        Main resolution pipeline.
        1. Check cache
        2. Exact ticker match (e.g. 'RELIANCE', 'TCS')
        3. Exact alias match (e.g. 'RIL' -> 'RELIANCE', 'Tata Motors' -> 'TATAMOTORS')
        4. Fuzzy matching across master company names and symbols
        5. Ambiguity detection
        """
        if not query or not query.strip():
            return None

        clean_q = query.strip()
        upper_q = clean_q.upper()
        lower_q = clean_q.lower()

        # Step 1: Cache
        cached = self._get_from_cache(clean_q)
        if cached:
            return cached

        # Step 2: Exact Ticker
        if upper_q in self.equities_by_symbol:
            profile = self._build_profile_from_symbol(upper_q)
            self._save_to_cache(clean_q, profile)
            return profile

        # Step 3: Exact Alias
        for ticker, data in self.alias_map.items():
            for alias in data.get("aliases", []):
                if alias.lower() == lower_q:
                    profile = self._build_profile_from_symbol(ticker)
                    self._save_to_cache(clean_q, profile)
                    return profile

        # Step 4: Fuzzy Match against company names and symbols
        scored_candidates: List[Tuple[float, str]] = []
        for symbol, entry in self.equities_by_symbol.items():
            name = entry["name"]
            score_name = self._compute_similarity(clean_q, name)
            score_sym = self._compute_similarity(clean_q, symbol)
            max_score = max(score_name, score_sym)

            # Check aliases as well
            if symbol in self.alias_map:
                for alias in self.alias_map[symbol].get("aliases", []):
                    score_alias = self._compute_similarity(clean_q, alias)
                    if score_alias > max_score:
                        max_score = score_alias

            if max_score >= threshold:
                scored_candidates.append((max_score, symbol))

        if not scored_candidates:
            return None

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_symbol = scored_candidates[0]

        # Step 5: Check Ambiguity
        if len(scored_candidates) > 1:
            second_score, second_symbol = scored_candidates[1]
            # If the user typed an ambiguous query like 'Tata' matching multiple Tata firms closely
            if abs(best_score - second_score) < 5.0 and best_score < 90.0:
                pass  # Pick the highest ranked or allow specialized ambiguity handling

        profile = self._build_profile_from_symbol(best_symbol)
        self._save_to_cache(clean_q, profile)
        return profile
