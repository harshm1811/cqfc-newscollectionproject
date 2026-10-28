"""
timestamp_parser.py - Robust Point-in-Time Timestamp Standardizer

CORE PRINCIPLE:
"Every discovered item should attempt to provide:
 published_at, first_seen_at, retrieved_at.
 Do not silently invent unavailable timestamps."

Responsibilities:
- Parse various date string formats (RFC 822 / RSS dates, ISO-8601, Indian date format).
- Convert all valid timestamps to UTC ISO-8601 string: 'YYYY-MM-DDTHH:MM:SSZ'.
- Return None if timestamp cannot be parsed or is missing. NEVER return current time as published_at.
"""

from typing import Optional
from datetime import datetime, timezone
import dateutil.parser


def parse_to_utc_iso(date_str: Optional[str]) -> Optional[str]:
    """
    Parses a raw date string and returns a standardized ISO-8601 UTC string.
    Returns None if date_str is empty or unparseable.
    """
    if not date_str or not isinstance(date_str, str) or not date_str.strip():
        return None
        
    try:
        # Use dateutil parser to handle varied RSS/API date formats
        dt = dateutil.parser.parse(date_str)
        if dt.tzinfo is None:
            # Assume UTC if naive, or convert from local if specified
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        return None


def get_current_utc_iso() -> str:
    """
    Returns current point-in-time timestamp in UTC ISO-8601 format.
    Used exclusively for first_seen_at and retrieved_at fields.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
