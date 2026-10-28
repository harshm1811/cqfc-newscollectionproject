"""
url_resolver.py - Google News & Media Redirect URL Resolver

Responsibilities:
- Resolves Google News intermediate links (https://news.google.com/rss/articles/CBMi...)
  to canonical destination publisher URLs.
- Employs HEAD requests or lightweight decoding with short timeouts to avoid blocking collection.
"""

from typing import Optional
import requests
from .logger import get_logger

logger = get_logger("url_resolver")


def resolve_google_redirect(url: str, session: Optional[requests.Session] = None, timeout: int = 5) -> str:
    """
    Attempts to follow redirects on Google News article links.
    Returns the resolved canonical URL, or original URL if resolution fails or times out.
    """
    if "news.google.com" not in url:
        return url
        
    s = session or requests.Session()
    try:
        resp = s.head(url, allow_redirects=True, timeout=timeout)
        if resp.url and "news.google.com" not in resp.url:
            return resp.url
    except Exception as e:
        logger.debug(f"Could not resolve redirect for {url}: {e}")
        
    return url
