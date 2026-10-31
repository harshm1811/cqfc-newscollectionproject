"""
resolver.py - Robust Typo-Tolerant Equity Resolver Engine

Primary Responsibilities:
1. Accept any user query, including typos, misspellings, letter transpositions, and informal slang:
   - 'Reliance', 'reliance', 'relaince', 'reLaince', 'Relancie' -> RELIANCE
   - 'SBI', 'SBI Bank', 'State Bank' -> SBIN
   - 'Tata Motors', 'tata motor', 'Tatamotrs', 'TaMo' -> TATAMOTORS
   - 'INFY', 'infosys', 'Infsys' -> INFY
   - 'L&T', 'Larsen', 'Larsen & Toubro' -> LT
   - 'HDFC', 'HDFC Bank' -> HDFCBANK
2. Full NSE listed universe coverage: ~2,600+ equities loaded from data/seed/nse_listed_companies.csv.
3. Multi-tier typo matching:
   - Tier 1: Exact ticker & alias dictionary (O(1))
   - Tier 2: Acronym / initials matching (e.g. SBI -> State Bank of India)
   - Tier 3: Damerau-Levenshtein transposition-aware edit distance & multi-token alignment
4. Local SQLite cache for instant re-resolution.
"""

from typing import Optional, List, Dict, Any, Tuple
import os
import csv
import json
import sqlite3
import difflib
import re
from pathlib import Path

from .profile import EquityProfile

try:
    from rapidfuzz import fuzz
    HAS_RAPIDFUZZ = True
except ImportError:
    HAS_RAPIDFUZZ = False


# Words that do not distinguish companies
STOPWORDS = {
    "limited", "ltd", "ltd.", "india", "ind", "corp", "corporation",
    "company", "co", "enterprises", "industries", "holdings", "group", "the"
}


# Major benchmark constituents (Nifty 50 / large-cap flagships)
# Used as intelligent tie-breakers when an ambiguous single-word query
# matches multiple conglomerates (e.g. 'Apolo' -> Apollo Hospitals over Apollo Tubes)
BENCHMARK_FLAGSHIPS = {
    "RELIANCE", "TCS", "HDFCBANK", "INFY", "ICICIBANK", "BHARTIARTL",
    "SBIN", "ITC", "LT", "HINDUNILVR", "BAJFINANCE", "MARUTI",
    "AXISBANK", "KOTAKBANK", "SUNPHARMA", "TITAN", "TATAMOTORS", "TATASTEEL",
    "NTPC", "POWERGRID", "ONGC", "COALINDIA", "ADANIENT", "ADANIPORTS",
    "ASIANPAINT", "M&M", "APOLLOHOSP", "NESTLEIND", "BAJAJFINSV", "JSWSTEEL",
    "TECHM", "WIPRO", "ULTRACEMCO", "GRASIM", "HINDALCO", "DRREDDY", "CIPLA"
}


def damerau_levenshtein_distance(s1: str, s2: str) -> int:
    """
    Computes Damerau-Levenshtein distance (accounts for insertions, deletions,
    substitutions, and transpositions of adjacent characters).
    """
    d = {}
    len1, len2 = len(s1), len(s2)
    for i in range(-1, len1 + 1):
        d[(i, -1)] = i + 1
    for j in range(-1, len2 + 1):
        d[(-1, j)] = j + 1

    for i in range(len1):
        for j in range(len2):
            cost = 0 if s1[i] == s2[j] else 1
            d[(i, j)] = min(
                d[(i - 1, j)] + 1,        # deletion
                d[(i, j - 1)] + 1,        # insertion
                d[(i - 1, j - 1)] + cost  # substitution
            )
            if i and j and s1[i] == s2[j - 1] and s1[i - 1] == s2[j]:
                d[(i, j)] = min(d[(i, j)], d[(i - 2, j - 2)] + cost)  # transposition

    return d[(len1 - 1, len2 - 1)]


def normalize_text(text: str) -> str:
    """Lowercases, removes special characters, and strips extra spaces."""
    cleaned = re.sub(r"[^\w\s]", " ", text.lower())
    return " ".join(cleaned.split())


def extract_core_tokens(text: str) -> List[str]:
    """Extracts non-stopword tokens from a company name."""
    words = normalize_text(text).split()
    meaningful = [w for w in words if w not in STOPWORDS]
    return meaningful if meaningful else words


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

        self.equities_by_symbol: Dict[str, Dict[str, Any]] = {}
        self.alias_map: Dict[str, Dict[str, Any]] = {}
        self.acronym_map: Dict[str, str] = {}

        self._load_seed_data()
        self._init_cache()

    def _load_seed_data(self) -> None:
        """Loads all NSE equities and curated alias seeds."""
        if self.seed_csv_path.exists():
            with open(self.seed_csv_path, mode="r", encoding="utf-8") as f:
                reader = csv.DictReader(f)
                for raw_row in reader:
                    # Strip whitespace from keys and values
                    row = {k.strip(): (v.strip() if v else "") for k, v in raw_row.items() if k}
                    symbol = (row.get("SYMBOL") or "").upper()
                    name = row.get("NAME OF COMPANY") or ""
                    isin = row.get("ISIN NUMBER") or ""
                    series = row.get("SERIES") or ""

                    entry = {
                        "symbol": symbol,
                        "name": name,
                        "isin": isin,
                        "series": series,
                        "core_tokens": extract_core_tokens(name)
                    }
                    if symbol:
                        self.equities_by_symbol[symbol] = entry

                    # Generate acronym from core tokens (e.g. State Bank of India -> sbi)
                    words = [w for w in re.findall(r"[A-Za-z]+", name) if w.lower() not in {"of", "and", "the"}]
                    if len(words) >= 2:
                        acronym = "".join(w[0] for w in words).lower()
                        if len(acronym) >= 2 and acronym not in self.acronym_map:
                            self.acronym_map[acronym] = symbol

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
        clean_q = normalize_text(query)
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
        clean_q = normalize_text(query)
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

    def _score_candidate(self, query_norm: str, query_tokens: List[str], symbol: str, entry: Dict[str, Any]) -> float:
        """
        Sophisticated candidate scoring:
        - Ticker edit distance
        - Token-level matching
        - Curated alias matching
        - Multi-word query alignment
        """
        sym_norm = normalize_text(symbol)
        max_sym_len = max(len(query_norm), len(sym_norm))
        sym_dist = damerau_levenshtein_distance(query_norm, sym_norm)
        sym_sim = (1.0 - (sym_dist / max_sym_len)) * 100.0 if max_sym_len else 0.0

        # Exact or near ticker match gets huge boost
        if sym_dist == 0:
            return 150.0

        core_tokens = entry.get("core_tokens", [])
        joined_core = "".join(core_tokens)
        joined_dist = damerau_levenshtein_distance(query_norm, joined_core)
        joined_max = max(len(query_norm), len(joined_core))
        joined_sim = (1.0 - (joined_dist / joined_max)) * 100.0 if joined_max else 0.0

        # Check query tokens against company core tokens
        token_sims = []
        for qt in query_tokens:
            best_t = max([
                (1.0 - (damerau_levenshtein_distance(qt, ct) / max(len(qt), len(ct)))) * 100.0
                for ct in core_tokens
            ] or [0.0])
            token_sims.append(best_t)

        avg_token_sim = sum(token_sims) / len(token_sims) if token_sims else 0.0
        all_tokens_high = all(s >= 75.0 for s in token_sims) if token_sims else False

        # Alias matching
        is_curated = symbol in self.alias_map
        alias_sims = []
        if is_curated:
            for a in self.alias_map[symbol].get("aliases", []):
                a_norm = normalize_text(a)
                a_dist = damerau_levenshtein_distance(query_norm, a_norm)
                a_max = max(len(query_norm), len(a_norm))
                alias_sims.append((1.0 - (a_dist / a_max)) * 100.0 if a_max else 0.0)

                # Joined alias without spaces
                a_joined = "".join(a_norm.split())
                aj_dist = damerau_levenshtein_distance(query_norm, a_joined)
                aj_max = max(len(query_norm), len(a_joined))
                alias_sims.append((1.0 - (aj_dist / aj_max)) * 100.0 if aj_max else 0.0)

        best_alias_sim = max(alias_sims or [0.0])

        score = max(sym_sim, avg_token_sim, joined_sim, best_alias_sim)

        # Multi-word full match bonus (e.g. 'tata' AND 'motors')
        if all_tokens_high and len(query_tokens) > 1:
            score += 25.0

        # Curated flagship equity boost
        if is_curated:
            score += 15.0

        # Prefer mainline Series EQ equities over illiquid BE/BZ
        if entry.get("series") == "EQ":
            score += 3.0

        # Benchmark flagship tie-breaker (e.g. Apollo Hospitals > Apollo Tubes on ambiguous single-word ties)
        if symbol in BENCHMARK_FLAGSHIPS:
            score += 4.0

        return score

    def resolve(self, query: str, threshold: float = 65.0) -> Optional[EquityProfile]:
        """
        Main resolution pipeline with multi-tier matching:
        1. Cache check
        2. Exact Ticker / Exact Alias (O(1))
        3. Acronym / Initials lookup
        4. Typo-tolerant candidate ranking
        """
        if not query or not str(query).strip():
            return None

        clean_q = normalize_text(query)
        raw_upper = "".join(ch for ch in query.upper() if ch.isalnum() or ch == '&')
        q_tokens = extract_core_tokens(clean_q)

        # 1. Check Cache
        cached = self._get_from_cache(clean_q)
        if cached:
            return cached

        # 2. Exact Ticker Match (case-insensitive)
        if raw_upper in self.equities_by_symbol:
            profile = self._build_profile_from_symbol(raw_upper)
            self._save_to_cache(clean_q, profile)
            return profile

        # 3. Exact Alias Match (e.g. 'RIL' -> 'RELIANCE', 'SBI' -> 'SBIN', 'L&T' -> 'LT')
        for ticker, data in self.alias_map.items():
            for alias in data.get("aliases", []):
                if normalize_text(alias) == clean_q or alias.upper() == raw_upper:
                    profile = self._build_profile_from_symbol(ticker)
                    self._save_to_cache(clean_q, profile)
                    return profile

        # 4. Check Acronym Map (e.g. 'sbi' -> 'SBIN', 'itc' -> 'ITC')
        if clean_q in self.acronym_map:
            profile = self._build_profile_from_symbol(self.acronym_map[clean_q])
            self._save_to_cache(clean_q, profile)
            return profile

        # 5. Fuzzy & Typo Matching across all listed companies
        scored_candidates: List[Tuple[float, str]] = []

        for symbol, entry in self.equities_by_symbol.items():
            score = self._score_candidate(clean_q, q_tokens, symbol, entry)
            if score >= threshold:
                scored_candidates.append((score, symbol))

        # Also check alias map entries that might not be in CSV
        for ticker in self.alias_map.keys():
            if ticker not in self.equities_by_symbol:
                mock_entry = {"symbol": ticker, "name": ticker, "core_tokens": [normalize_text(ticker)], "series": "EQ"}
                score = self._score_candidate(clean_q, q_tokens, ticker, mock_entry)
                if score >= threshold:
                    scored_candidates.append((score, ticker))

        if not scored_candidates:
            return None

        # Sort descending by score
        scored_candidates.sort(key=lambda x: x[0], reverse=True)
        best_score, best_symbol = scored_candidates[0]

        profile = self._build_profile_from_symbol(best_symbol)
        self._save_to_cache(clean_q, profile)
        return profile
