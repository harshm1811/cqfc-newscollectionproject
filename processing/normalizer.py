"""
processing/normalizer.py - Field and timestamp normalization for financial news records.

Normalizes:
- URLs (canonical scheme/host, path normalization, stripping tracking params)
- Timestamps (RFC 3339 / ISO 8601 UTC string format: YYYY-MM-DDTHH:MM:SSZ; never invents timestamps)
- Publisher names (standardized casing and known aliases)
- Company names & Tickers (uppercase tickers, normalized whitespace)
- Character encoding
"""

from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
import re
from typing import Any, Dict, List, Optional
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from dateutil import parser as date_parser

TRACKING_QUERY_PARAMS = {
    "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
    "gclid", "fbclid", "mc_cid", "mc_eid", "ref", "ref_src", "fb_action_ids",
    "fb_action_types", "ncid", "sr_share", "_ga", "_gl",
}

KNOWN_PUBLISHERS = {
    "economictimes": "Economic Times",
    "economictimes.indiatimes.com": "Economic Times",
    "livemint": "Mint",
    "livemint.com": "Mint",
    "reuters": "Reuters",
    "reuters.com": "Reuters",
    "bloomberg": "Bloomberg",
    "bloomberg.com": "Bloomberg",
    "bse": "BSE",
    "bseindia.com": "BSE",
    "nse": "NSE",
    "nseindia.com": "NSE",
    "sebi": "SEBI",
    "sebi.gov.in": "SEBI",
    "cnbctv18": "CNBC-TV18",
    "cnbctv18.com": "CNBC-TV18",
    "business-standard": "Business Standard",
    "businessstandard": "Business Standard",
    "business-standard.com": "Business Standard",
    "financialexpress": "Financial Express",
    "financialexpress.com": "Financial Express",
}


def normalize_url(url: Optional[str]) -> str:
    """Standardize URL: lowercase host/scheme, remove tracking parameters, normalize path."""
    if not url or not isinstance(url, str) or not url.strip():
        return ""
    try:
        parts = urlsplit(url.strip())
        scheme = (parts.scheme or "https").lower()
        host = parts.netloc.lower()
        if host.startswith("www."):
            host = host[4:]
        # Strip default ports
        if host.endswith(":80") and scheme == "http":
            host = host[:-3]
        elif host.endswith(":443") and scheme == "https":
            host = host[:-4]

        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")

        # Filter tracking params
        kept_params = []
        for k, v in parse_qsl(parts.query, keep_blank_values=True):
            if k.lower() not in TRACKING_QUERY_PARAMS:
                kept_params.append((k, v))
        new_query = urlencode(kept_params)

        return urlunsplit((scheme, host, path, new_query, ""))
    except Exception:
        return url.strip().casefold()


def normalize_timestamp(ts: Any) -> Optional[str]:
    """
    Convert datetime or string into ISO 8601 UTC string: YYYY-MM-DDTHH:MM:SSZ.
    CRITICAL: Never silently invent missing timestamps!
    Returns None if missing or unparseable.
    """
    if ts is None:
        return None
    if isinstance(ts, datetime):
        dt = ts
    elif isinstance(ts, str):
        cleaned = ts.strip()
        if not cleaned:
            return None
        try:
            dt = date_parser.parse(cleaned)
        except Exception:
            return None
    elif isinstance(ts, (int, float)):
        # Epoch timestamp in seconds or milliseconds
        val = float(ts)
        if val > 1e11:  # milliseconds
            val /= 1000.0
        try:
            dt = datetime.fromtimestamp(val, tz=timezone.utc)
        except Exception:
            return None
    else:
        return None

    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    else:
        dt = dt.astimezone(timezone.utc)

    return dt.strftime("%Y-%m-%dT%H:%M:%SZ")


def normalize_publisher(source: Optional[str], url: Optional[str] = None) -> str:
    """Normalize publisher name using known financial media aliases."""
    if source and isinstance(source, str) and source.strip():
        cleaned = " ".join(source.strip().split())
        key = cleaned.lower().replace(" ", "").replace("-", "")
        if key in KNOWN_PUBLISHERS:
            return KNOWN_PUBLISHERS[key]
        return cleaned

    # Fallback to domain name from URL
    if url and isinstance(url, str) and url.strip():
        try:
            host = urlsplit(url).netloc.lower()
            if host.startswith("www."):
                host = host[4:]
            if host in KNOWN_PUBLISHERS:
                return KNOWN_PUBLISHERS[host]
            # Strip TLD
            domain_name = host.split(".")[0]
            return domain_name.capitalize()
        except Exception:
            pass

    return "Unknown"


def normalize_source_type(source_type: Optional[str], source: str, primary_source: bool) -> str:
    """Normalize the supplied type without inferring official status from a name."""
    if not isinstance(source_type, str) or not source_type.strip():
        return "UNKNOWN" if primary_source else "NEWS_RSS"

    st = source_type.strip().upper().replace("-", "_").replace(" ", "_")
    valid = {
        "NEWS_RSS", "EXCHANGE_FILING", "REGULATORY", "REGULATORY_ANNOUNCEMENT",
        "COMPANY_IR", "PRESS_RELEASE", "AGGREGATOR", "UNKNOWN"
    }
    return st if st in valid else "UNKNOWN"


def _explicit_boolean(value: Any, default: bool = False) -> bool:
    """Read an explicit provenance flag without Python's bool('false') trap."""
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        cleaned = value.strip().casefold()
        if cleaned in {"true", "1", "yes"}:
            return True
        if cleaned in {"false", "0", "no"}:
            return False
    if isinstance(value, (int, float)) and value in (0, 1):
        return bool(value)
    return default


def normalize_article(article: Dict[str, Any]) -> Dict[str, Any]:
    """Normalize a single article record while preserving original data."""
    raw = deepcopy(article)
    norm = dict(article)
    if "original_record" not in norm:
        norm["original_record"] = raw

    validation_flags: List[str] = []

    # 1. URL
    norm["url"] = normalize_url(norm.get("url"))
    if not norm["url"]:
        validation_flags.append("missing_url")

    # 2. Ticker & Company Name
    ticker = str(norm.get("ticker") or "").strip().upper()
    norm["ticker"] = ticker
    if not ticker:
        validation_flags.append("missing_ticker")

    company_name = str(norm.get("company_name") or "").strip()
    norm["company_name"] = " ".join(company_name.split()) if company_name else ""

    # 3. Timestamps (never invent missing dates!)
    norm["published_at"] = normalize_timestamp(norm.get("published_at"))
    norm["first_seen_at"] = normalize_timestamp(norm.get("first_seen_at"))
    if not norm["published_at"]:
        validation_flags.append("missing_published_at")

    # 4. Source & Primary source
    # Provenance is supplied by the collector. Publisher names and URLs do not
    # prove that a record is an official filing or regulatory release.
    is_primary = _explicit_boolean(norm.get("primary_source"), default=False)
    norm["primary_source"] = is_primary

    norm["source"] = normalize_publisher(norm.get("source"), norm.get("url"))
    norm["source_type"] = normalize_source_type(norm.get("source_type"), norm["source"], is_primary)

    # 5. Title & Text validation
    title = str(norm.get("title") or "").strip()
    norm["title"] = " ".join(title.split())
    if not norm["title"]:
        validation_flags.append("missing_title")

    norm["validation_flags"] = validation_flags
    return norm


def normalize_articles(articles: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """Batch normalize articles, returning cleaned and verified records."""
    from .cleaner import clean_article_text
    output = []
    for art in articles:
        normalized = normalize_article(art)
        cleaned = clean_article_text(normalized)
        output.append(cleaned)
    return output
