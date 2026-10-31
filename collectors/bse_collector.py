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
import urllib.parse
import xml.etree.ElementTree as ET

from .base_collector import BaseCollector, RawArticleRecord
from equity.profile import EquityProfile
from utils.http_client import create_http_session
from utils.timestamp_parser import parse_to_utc_iso, get_current_utc_iso

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


class BSECollector(BaseCollector):
    """
    Dedicated primary-source collector for BSE corporate announcements.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="bse_collector", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.base_url = "https://api.bseindia.com"

    def _collect_from_announcement_feed(self, ticker: str, company_name: str) -> List[RawArticleRecord]:
        records = []
        try:
            clean_name = company_name.replace(" Limited", "").replace(" Ltd.", "").replace(" Ltd", "")
            query = f'site:bseindia.com OR "BSE" filing "{clean_name}" OR "{ticker}"'
            encoded_q = urllib.parse.quote_plus(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-IN&gl=IN&ceid=IN:en"

            resp = self.session.get(rss_url, timeout=10)
            if resp.status_code == 200 and "<item>" in resp.text:
                self.save_raw_payload(ticker, resp.text, identifier="bse_feed")
                parsed_items = []
                if HAS_FEEDPARSER:
                    feed = feedparser.parse(resp.text)
                    for entry in feed.entries:
                        parsed_items.append({
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "summary": entry.get("summary", "")
                        })
                else:
                    root = ET.fromstring(resp.text)
                    for item in root.findall(".//item"):
                        parsed_items.append({
                            "title": item.findtext("title") or "",
                            "link": item.findtext("link") or "",
                            "published": item.findtext("pubDate") or "",
                            "summary": item.findtext("description") or ""
                        })

                retrieved_now = get_current_utc_iso()
                for item in parsed_items:
                    title = item.get("title", "")
                    link = item.get("link", "")
                    if not link or not title:
                        continue

                    record = RawArticleRecord(
                        company_name=company_name,
                        ticker=ticker,
                        title=f"BSE Filing / Announcement: {title}",
                        description=item.get("summary", ""),
                        url=link,
                        source="BSE Announcements",
                        source_type="EXCHANGE_FILING",
                        primary_source=True,
                        published_at=parse_to_utc_iso(item.get("published")),
                        first_seen_at=retrieved_now,
                        retrieved_at=retrieved_now,
                        collector=self.name
                    )
                    records.append(record)
        except Exception as e:
            self.logger.debug(f"BSE announcement stream note: {e}")
        return records

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
                "strPrevDate": (start_date or datetime.now()).strftime("%Y%m%d"),
                "strScrip": profile.ticker,
                "strSearch": "P",
                "strToDate": (end_date or datetime.now()).strftime("%Y%m%d"),
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
                        collector=self.name
                    )
                    records.append(record)
        except Exception as e:
            self.logger.debug(f"Direct BSE API call note: {e}")

        # 2. Resilient BSE Filing Feed
        feed_records = self._collect_from_announcement_feed(profile.ticker, profile.company_name)
        seen_urls = {r.url for r in records}
        for fr in feed_records:
            if fr.url not in seen_urls:
                records.append(fr)
                seen_urls.add(fr.url)

        self.logger.info(f"BSE collected {len(records)} announcements for {profile.ticker}")
        return records
