"""
timestamp_parser.py - Robust Point-in-Time Timestamp Standardizer

CORE PRINCIPLES (Group 1 Project Spec):
1. "Every discovered item should attempt to provide:
    published_at, first_seen_at, retrieved_at."
2. "Do not silently invent unavailable timestamps."
   If an article has no publication date or is unparseable, published_at MUST be None (null).
3. All valid timestamps must be normalized to UTC ISO-8601: 'YYYY-MM-DDTHH:MM:SSZ'.
4. Supports RFC-822 / RSS formats, ISO-8601, and Indian financial formats (DD-MMM-YYYY, DD/MM/YYYY).
"""

from typing import Optional
from datetime import datetime, timezone
import email.utils
import re

try:
    import dateutil.parser
    HAS_DATEUTIL = True
except ImportError:
    HAS_DATEUTIL = False


# Common Indian exchange date patterns (e.g. "27-Oct-2026 14:30:00", "28/10/2026 09:15:00")
CUSTOM_FORMATS = [
    "%d-%b-%Y %H:%M:%S",
    "%d-%b-%Y %H:%M",
    "%d-%B-%Y %H:%M:%S",
    "%d-%m-%Y %H:%M:%S",
    "%d/%m/%Y %H:%M:%S",
    "%d-%b-%Y",
    "%d/%m/%Y",
    "%Y-%m-%d %H:%M:%S",
    "%Y-%m-%dT%H:%M:%S",
    "%Y-%m-%d"
]


def parse_to_utc_iso(date_str: Optional[str]) -> Optional[str]:
    """
    Parses a raw date string and returns a standardized ISO-8601 UTC string:
    'YYYY-MM-DDTHH:MM:SSZ'
    
    Returns None if date_str is empty, null, or unparseable.
    CRITICAL: Never invents dates or returns current time for published_at.
    """
    if not date_str or not isinstance(date_str, str):
        return None

    clean_str = date_str.strip()
    if not clean_str or clean_str.lower() in {"none", "null", "undefined", "n/a", ""}:
        return None

    # 1. Try dateutil if available
    if HAS_DATEUTIL:
        try:
            dt = dateutil.parser.parse(clean_str)
            if dt.tzinfo is None:
                # Default Indian timezone (IST = UTC+5:30) for naive exchange dates if indicated
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            pass

    # 2. Try RFC-2822 / RSS date format (standard for RSS feeds)
    try:
        parsed_tuple = email.utils.parsedate_to_datetime(clean_str)
        if parsed_tuple:
            if parsed_tuple.tzinfo is None:
                parsed_tuple = parsed_tuple.replace(tzinfo=timezone.utc)
            else:
                parsed_tuple = parsed_tuple.astimezone(timezone.utc)
            return parsed_tuple.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # 3. Try standard ISO-8601 formats
    try:
        iso_clean = clean_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso_clean)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    except Exception:
        pass

    # 4. Try manual custom exchange formats
    for fmt in CUSTOM_FORMATS:
        try:
            dt = datetime.strptime(clean_str, fmt)
            dt = dt.replace(tzinfo=timezone.utc)
            return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
        except Exception:
            continue

    # Cannot parse accurately -> strictly return None
    return None


def get_current_utc_iso() -> str:
    """
    Returns current point-in-time timestamp in UTC ISO-8601 format.
    Used strictly for first_seen_at and retrieved_at fields.
    """
    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
