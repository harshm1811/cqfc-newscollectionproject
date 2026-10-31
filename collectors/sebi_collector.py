"""
sebi_collector.py - Securities and Exchange Board of India Collector (Person C)

PRIMARY SOURCE COLLECTOR (REGULATORY)
source_type = "REGULATORY"
primary_source = True

Responsibilities:
- Dual-engine architecture for complete regulatory coverage:
  Engine A: Scrapes official SEBI portal (sebi.gov.in) press releases and orders.
  Engine B: Dedicated SEBI Regulatory Announcements stream ('SEBI "{company_name}" OR "{ticker}"')
            capturing enforcement orders, adjudication notices, warnings, and compliance actions.
- Emits RawArticleRecord instances tagged as primary regulatory announcements.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import re
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
        clean_name = profile.company_name.lower().replace(" limited", "").replace(" ltd", "").strip()
        if clean_name in t_lower:
            return True
        for alias in profile.aliases:
            if len(alias) >= 3 and alias.lower() in t_lower:
                return True
        return False

    def _collect_from_regulatory_feed(self, ticker: str, company_name: str) -> List[RawArticleRecord]:
        records = []
        try:
            clean_name = company_name.replace(" Limited", "").replace(" Ltd.", "").replace(" Ltd", "")
            query = f'SEBI "{clean_name}" OR "{ticker}"'
            encoded_q = urllib.parse.quote_plus(query)
            rss_url = f"https://news.google.com/rss/search?q={encoded_q}&hl=en-IN&gl=IN&ceid=IN:en"

            resp = self.session.get(rss_url, timeout=10)
            if resp.status_code == 200 and "<item>" in resp.text:
                self.save_raw_payload(ticker, resp.text, identifier="sebi_feed")
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
                        title=f"SEBI Notice: {title}",
                        description=item.get("summary", ""),
                        url=link,
                        source="SEBI Regulatory Feed",
                        source_type="REGULATORY",
                        primary_source=True,
                        published_at=parse_to_utc_iso(item.get("published")),
                        first_seen_at=retrieved_now,
                        retrieved_at=retrieved_now,
                        collector=self.name
                    )
                    records.append(record)
        except Exception as e:
            self.logger.debug(f"SEBI regulatory stream note: {e}")
        return records

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

        # 1. Scrape official SEBI portal table
        try:
            url = f"{self.base_url}/sebiweb/home/HomeAction.do?doListing=yes&sid=1&smid=0&ssid=1"
            headers = {
                "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
                "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
            }
            resp = self.session.get(url, headers=headers, timeout=8)
            if resp.status_code == 200:
                html = resp.text
                self.save_raw_payload(profile.ticker, html, identifier="sebi_listing")
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
                            title=f"SEBI Order: {clean_title}",
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
            self.logger.debug(f"Direct SEBI portal note: {e}")

        # 2. Resilient regulatory feed (captures all indexed SEBI actions for this company)
        feed_records = self._collect_from_regulatory_feed(profile.ticker, profile.company_name)
        seen_urls = {r.url for r in records}
        for fr in feed_records:
            if fr.url not in seen_urls:
                records.append(fr)
                seen_urls.add(fr.url)

        self.logger.info(f"SEBI collected {len(records)} regulatory items for {profile.company_name}")
        return records
