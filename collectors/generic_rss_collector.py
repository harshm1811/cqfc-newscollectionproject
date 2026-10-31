"""
generic_rss_collector.py - General Financial Media RSS Collector (Person B)

Responsibilities:
- Monitors major Indian financial feeds:
    * Economic Times (Markets, Stocks)
    * Livemint (Companies, Industry)
    * Business Standard (Finance)
    * Yahoo Finance Equity Feed ({TICKER}.NS)
- Emits RawArticleRecord objects with source_type="NEWS_RSS" or "AGGREGATOR".
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
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


class GenericRSSCollector(BaseCollector):
    """
    Scrapes public financial RSS feeds and equity-specific feeds for company mentions.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="generic_rss", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.feeds = (config or {}).get("collectors", {}).get("generic_rss", {}).get("feeds", [
            {"name": "Livemint Companies", "url": "https://www.livemint.com/rss/companies"},
            {"name": "Economic Times Markets", "url": "https://economictimes.indiatimes.com/markets/stocks/rssfeeds/2146842.cms"},
            {"name": "Business Standard Finance", "url": "https://www.business-standard.com/rss/finance-103.rss"}
        ])

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
        for sub in profile.important_businesses:
            if len(sub) >= 3 and sub.lower() in t_lower:
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
        Parses configured external RSS feeds and equity ticker feeds.
        """
        self.logger.info(f"Starting Generic RSS collection for {profile.ticker}")
        records: List[RawArticleRecord] = []
        seen_urls = set()

        # Combine static feeds + dynamic Yahoo Finance ticker feed
        all_feeds = list(self.feeds)
        all_feeds.append({
            "name": f"Yahoo Finance ({profile.ticker})",
            "url": f"https://feeds.finance.yahoo.com/rss/2.0/headline?s={profile.ticker}.NS&region=IN&lang=en-IN"
        })

        for feed_info in all_feeds:
            feed_name = feed_info.get("name", "Financial RSS")
            feed_url = feed_info.get("url")
            if not feed_url:
                continue

            try:
                resp = self.session.get(feed_url, timeout=8)
                if resp.status_code != 200:
                    continue

                raw_xml = resp.text
                if "<item>" not in raw_xml:
                    continue

                self.save_raw_payload(profile.ticker, raw_xml, identifier=feed_name.replace(" ", "_"))

                parsed_items = []
                if HAS_FEEDPARSER:
                    feed = feedparser.parse(raw_xml)
                    for entry in feed.entries:
                        parsed_items.append({
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "summary": entry.get("summary", ""),
                            "source": feed_name
                        })
                else:
                    root = ET.fromstring(raw_xml)
                    for item in root.findall(".//item"):
                        parsed_items.append({
                            "title": item.findtext("title") or "",
                            "link": item.findtext("link") or "",
                            "published": item.findtext("pubDate") or "",
                            "summary": item.findtext("description") or "",
                            "source": feed_name
                        })

                retrieved_now = get_current_utc_iso()

                for item in parsed_items:
                    link = item.get("link", "").strip()
                    title = item.get("title", "").strip()
                    summary = item.get("summary", "").strip()

                    if not link or not title or link in seen_urls:
                        continue

                    # If it's a general front-page feed, filter for equity match.
                    # If it's an equity-specific ticker feed, all articles belong to this equity!
                    is_equity_feed = f"{profile.ticker}.NS" in feed_url
                    if not is_equity_feed and not self._matches_equity(f"{title} {summary}", profile):
                        continue

                    seen_urls.add(link)

                    record = RawArticleRecord(
                        company_name=profile.company_name,
                        ticker=profile.ticker,
                        title=title,
                        description=summary,
                        url=link,
                        source=feed_name,
                        source_type="NEWS_RSS",
                        primary_source=False,
                        published_at=parse_to_utc_iso(item.get("published")),
                        first_seen_at=retrieved_now,
                        retrieved_at=retrieved_now,
                        collector=self.name
                    )
                    records.append(record)

            except Exception as e:
                self.logger.debug(f"Feed '{feed_name}' notice: {e}")

        self.logger.info(f"Generic RSS collected {len(records)} relevant items for {profile.ticker}")
        return records
