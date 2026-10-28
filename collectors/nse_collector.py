"""
nse_collector.py - National Stock Exchange (NSE) Announcements Collector (Person C)

PRIMARY SOURCE COLLECTOR
source_type = "EXCHANGE_FILING"
primary_source = True

Responsibilities:
- Fetches official corporate announcements filed with NSE India.
- Handles NSE session priming (cookies and browser headers).
- Parses corporate announcement JSON payload for the specified ticker.
- Preserves raw response to data/raw/{ticker}/.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import json
import time

from .base_collector import BaseCollector, RawArticleRecord
from equity.profile import EquityProfile
from utils.http_client import create_http_session
from utils.timestamp_parser import parse_to_utc_iso, get_current_utc_iso


class NSECollector(BaseCollector):
    """
    Dedicated primary-source collector for NSE corporate filings.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="nse_collector", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.base_url = "https://www.nseindia.com"
        self._session_primed = False

    def _prime_session(self) -> bool:
        """
        NSE requires visiting the base domain to establish session cookies.
        """
        try:
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
                "Accept-Language": "en-US,en;q=0.9"
            }
            resp = self.session.get(self.base_url, headers=headers, timeout=10)
            if resp.status_code == 200:
                self._session_primed = True
                return True
        except Exception as e:
            self.logger.debug(f"Failed to prime NSE session: {e}")
        return False

    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Fetches corporate announcements for profile.ticker from NSE.
        """
        self.logger.info(f"Starting NSE collection for {profile.ticker}")
        records: List[RawArticleRecord] = []

        try:
            if not self._session_primed:
                self._prime_session()

            endpoint = f"{self.base_url}/api/corporate-announcements?index=equities&symbol={profile.ticker}"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
                "Referer": f"{self.base_url}/companies-listing/corporate-filings/announcements",
                "Accept": "application/json, text/plain, */*"
            }

            resp = self.session.get(endpoint, headers=headers, timeout=12)
            if resp.status_code == 200:
                try:
                    data = resp.json()
                    self.save_raw_payload(profile.ticker, data, identifier="nse_announcements")

                    items = data if isinstance(data, list) else data.get("data", [])
                    retrieved_now = get_current_utc_iso()

                    for item in items:
                        desc = item.get("desc", "") or item.get("an_dt", "")
                        subject = item.get("attmntNm") or item.get("sm_name") or desc
                        attmnt_url = item.get("attmnt", "")
                        if attmnt_url and not attmnt_url.startswith("http"):
                            attmnt_url = f"{self.base_url}{attmnt_url}"

                        pub_date = item.get("an_dt") or item.get("broadcastDate")

                        record = RawArticleRecord(
                            company_name=profile.company_name,
                            ticker=profile.ticker,
                            title=f"NSE Filing: {desc[:120]}",
                            description=str(subject),
                            url=attmnt_url or f"{self.base_url}/get-quotes/equity?symbol={profile.ticker}",
                            source="NSE",
                            source_type="EXCHANGE_FILING",
                            primary_source=True,
                            published_at=parse_to_utc_iso(pub_date),
                            first_seen_at=retrieved_now,
                            retrieved_at=retrieved_now,
                            collector=self.name
                        )
                        records.append(record)
                except Exception as json_err:
                    self.logger.warning(f"Could not parse NSE JSON response: {json_err}")
            else:
                self.logger.warning(f"NSE announcement endpoint returned HTTP {resp.status_code}")

        except Exception as e:
            self.logger.warning(f"NSE collection failed gracefully: {e}")

        self.logger.info(f"NSE collected {len(records)} announcements for {profile.ticker}")
        return records
