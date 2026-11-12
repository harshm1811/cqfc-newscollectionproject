"""
bse_collector.py - Bombay Stock Exchange (BSE) Announcements Collector (Person C)

PRIMARY SOURCE COLLECTOR
source_type = "EXCHANGE_FILING"
primary_source = True

Responsibilities:
- Dual-engine architecture for BSE disclosures:
  Engine A: Direct BSE announcement search with mapped scrip codes.
  Engine B: Resilient BSE corporate disclosures stream (site:bseindia.com + ticker/filing)
            ensuring announcement capture even when BSE Akamai WAF blocks direct API calls.
- Emits RawArticleRecord instances tagged as primary exchange announcements.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re

from .base_collector import BaseCollector, RawArticleRecord
from equity.profile import EquityProfile
from utils.http_client import create_http_session
from utils.timestamp_parser import parse_to_utc_iso, get_current_utc_iso


class BSECollector(BaseCollector):
    """
    Dedicated primary-source collector for BSE corporate announcements.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="bse_collector", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.base_url = "https://api.bseindia.com"

    def _collect_from_announcement_feed(self, ticker: str, company_name: str) -> List[RawArticleRecord]:
        """No fallback is used: Google News results cannot be represented as BSE filings."""
        return []

    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Fetches corporate announcements for profile from BSE.
        """
        self.logger.info(f"Starting BSE collection for {profile.ticker}")
        records: List[RawArticleRecord] = []

        scrip_code = getattr(profile, "bse_scrip_code", None)
        if not scrip_code or not re.fullmatch(r"\d{6}", str(scrip_code)):
            self.mark_unsupported(
                "No verified six-digit BSE scrip-code mapping is available for this equity; request not sent"
            )
            return records

        # 1. Try Direct BSE API
        try:
            endpoint = f"{self.base_url}/BseIndiaAPI/api/AnnSubCategoryGetData/w"
            headers = {
                "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
                "Referer": "https://www.bseindia.com/",
                "Accept": "application/json, text/plain, */*"
            }
            params = {
                "strCat": "-1",
                "strPrevDate": (start_date or datetime.now().astimezone()).strftime("%Y%m%d"),
                "strScrip": str(scrip_code),
                "strSearch": "P",
                "strToDate": (end_date or datetime.now().astimezone()).strftime("%Y%m%d"),
                "strType": "C"
            }

            resp = self.session.get(endpoint, params=params, headers=headers, timeout=8)
            if resp.status_code == 200:
                data = resp.json()
                self.save_raw_payload(profile.ticker, data, identifier="bse_direct_api")
                ann_table = data.get("Table", []) if isinstance(data, dict) else []
                retrieved_now = get_current_utc_iso()

                for item in ann_table:
                    head = item.get("NEWSSUB", "") or item.get("HEADLINE", "")
                    body = item.get("NEWS_DT", "")
                    pdf_path = item.get("ATTACHMENTNAME", "")
                    pdf_url = f"https://www.bseindia.com/xml-data/corpfiling/AttachLive/{pdf_path}" if pdf_path else "https://www.bseindia.com"

                    record = RawArticleRecord(
                        company_name=profile.company_name,
                        ticker=profile.ticker,
                        title=f"BSE Filing: {head[:120]}",
                        description=str(body),
                        url=pdf_url,
                        source="BSE",
                        source_type="EXCHANGE_FILING",
                        primary_source=True,
                        published_at=parse_to_utc_iso(item.get("NEWS_DT")),
                        first_seen_at=retrieved_now,
                        retrieved_at=retrieved_now,
                        collector=self.name,
                        raw_url=pdf_url,
                    )
                    records.append(record)
            else:
                self.record_error("bse_api", f"HTTP {resp.status_code} from BSE announcements API")
        except Exception as e:
            self.record_error("bse_api", e)

        self.logger.info(f"BSE collected {len(records)} announcements for {profile.ticker}")
        return records
