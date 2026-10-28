"""
sebi_collector.py - Securities and Exchange Board of India Collector (Person C)

PRIMARY SOURCE COLLECTOR (REGULATORY)
source_type = "REGULATORY"
primary_source = True

Responsibilities:
- Monitors SEBI press releases and adjudication/enforcement orders.
- Scrapes listing pages from sebi.gov.in.
- Filters entries by company name or major promoters.
- Emits RawArticleRecord instances.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re

from .base_collector import BaseCollector, RawArticleRecord
from equity.profile import EquityProfile
from utils.http_client import create_http_session
from utils.timestamp_parser import parse_to_utc_iso, get_current_utc_iso


class SEBICollector(BaseCollector):
    """
    Dedicated regulatory collector for SEBI orders and press statements.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="sebi_collector", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.base_url = "https://www.sebi.gov.in"

    def _matches_equity(self, text: str, profile: EquityProfile) -> bool:
        t_lower = text.lower()
        if profile.ticker.lower() in t_lower:
            return True
        if profile.company_name.lower() in t_lower:
            return True
        for alias in profile.aliases:
            if alias.lower() in t_lower:
                return True
        return False

    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Fetches and filters SEBI regulatory updates matching company name/promoter.
        """
        self.logger.info(f"Starting SEBI collection for {profile.company_name}")
        records: List[RawArticleRecord] = []

        try:
            # SEBI Public Press Releases Listing
            url = f"{self.base_url}/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=1"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            resp = self.session.get(url, headers=headers, timeout=12)
            if resp.status_code == 200:
                html = resp.text
                self.save_raw_payload(profile.ticker, html, identifier="sebi_listing")

                # Basic regex extraction of rows from the listing table: <a href="(?P<url>[^"]+)">(?P<title>[^<]+)</a>
                matches = re.findall(r'<a\s+href=["\']([^"\']+)["\'][^>]*>([^<]+)</a>', html)
                retrieved_now = get_current_utc_iso()

                for link, title in matches:
                    clean_title = title.strip()
                    if not clean_title or len(clean_title) < 10:
                        continue

                    if self._matches_equity(clean_title, profile):
                        full_url = link if link.startswith("http") else f"{self.base_url}/{link.lstrip('/')}"
                        record = RawArticleRecord(
                            company_name=profile.company_name,
                            ticker=profile.ticker,
                            title=f"SEBI Notice: {clean_title}",
                            description=clean_title,
                            url=full_url,
                            source="SEBI",
                            source_type="REGULATORY",
                            primary_source=True,
                            published_at=None,
                            first_seen_at=retrieved_now,
                            retrieved_at=retrieved_now,
                            collector=self.name
                        )
                        records.append(record)

        except Exception as e:
            self.logger.warning(f"SEBI collection failed gracefully: {e}")

        self.logger.info(f"SEBI collected {len(records)} regulatory items for {profile.company_name}")
        return records
