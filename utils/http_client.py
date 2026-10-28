"""
http_client.py - Hardened Requests Session with Retries & User-Agent Rotation

Responsibilities:
- Configure polite HTTP requests with automatic retries on status codes 429, 500, 502, 503, 504.
- Implement exponential backoff to handle transient network/server glitches.
- Manage realistic desktop User-Agent headers to avoid false-positive bot blocks.
"""

import random
import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Optional, List


DEFAULT_USER_AGENTS = [
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/121.0.0.0 Safari/537.36",
    "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/119.0.0.0 Safari/537.36"
]


def create_http_session(
    retries: int = 3,
    backoff_factor: float = 1.0,
    status_forcelist: Optional[List[int]] = None,
    user_agents: Optional[List[str]] = None
) -> requests.Session:
    """
    Creates and returns a requests.Session configured with retries and headers.
    """
    if status_forcelist is None:
        status_forcelist = [429, 500, 502, 503, 504]
        
    agents = user_agents or DEFAULT_USER_AGENTS
    
    session = requests.Session()
    retry_strategy = Retry(
        total=retries,
        backoff_factor=backoff_factor,
        status_forcelist=status_forcelist,
        allowed_methods=["HEAD", "GET", "POST"]
    )
    
    adapter = HTTPAdapter(max_retries=retry_strategy)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    session.headers.update({
        "User-Agent": random.choice(agents),
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8",
        "Accept-Language": "en-US,en;q=0.9",
    })
    
    return session
