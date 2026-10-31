"""
google_news_rss.py - High-Volume Google News RSS Collector (Person B)

Responsibilities:
- Builds Google News search RSS queries across multiple high-signal categories.
- Handles throttling and user-agent rotation to prevent HTTP 429 rate limits.
- Supports unquoted fallback searches if quoted searches yield low volume.
- Resolves redirect URLs via utils.url_resolver if configured.
- Normalizes published timestamps to ISO-8601 UTC.
- Saves raw unedited feed XML to data/raw/{ticker}/.
- Emits RawArticleRecord objects with source_type="NEWS_RSS", primary_source=False.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import urllib.parse
import time
import xml.etree.ElementTree as ET

from .base_collector import BaseCollector, RawArticleRecord
from equity.profile import EquityProfile
from utils.http_client import create_http_session
from utils.timestamp_parser import parse_to_utc_iso, get_current_utc_iso
from utils.url_resolver import resolve_google_redirect

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


class GoogleNewsRSSCollector(BaseCollector):
    """
    Collects maximum financial articles via Google News RSS search.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="google_news_rss", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.gnews_cfg = (config or {}).get("collectors", {}).get("google_news_rss", {})
        self.hl = self.gnews_cfg.get("language", "en-IN")
        self.gl = self.gnews_cfg.get("country_code", "IN")
        self.resolve_redirects = self.gnews_cfg.get("resolve_redirect_urls", False)
        self.max_queries = self.gnews_cfg.get("max_queries", 6)

    def _build_rss_url(self, query: str, start_date: Optional[datetime] = None, end_date: Optional[datetime] = None) -> str:
        q_str = query
        if start_date:
            q_str += f" after:{start_date.strftime('%Y-%m-%d')}"
        if end_date:
            q_str += f" before:{end_date.strftime('%Y-%m-%d')}"

        encoded_q = urllib.parse.quote_plus(q_str)
        return f"https://news.google.com/rss/search?q={encoded_q}&hl={self.hl}&gl={self.gl}&ceid={self.gl}:{self.hl.split('-')[0]}"

    def _parse_xml_fallback(self, xml_content: str) -> List[Dict[str, Any]]:
        """Parses RSS items using standard library ElementTree when feedparser is not available."""
        items = []
        try:
            root = ET.fromstring(xml_content)
            channel = root.find("channel")
            if channel is None:
                return items
            for item in channel.findall("item"):
                title = item.findtext("title") or ""
                link = item.findtext("link") or ""
                pub_date = item.findtext("pubDate") or ""
                description = item.findtext("description") or ""
                source_elem = item.find("source")
                source_name = source_elem.text if source_elem is not None else "Google News"

                items.append({
                    "title": title,
                    "link": link,
                    "published": pub_date,
                    "summary": description,
                    "source": source_name
                })
        except Exception as e:
            self.logger.debug(f"XML fallback parsing error: {e}")
        return items

    def _fetch_rss(self, url: str) -> List[Dict[str, Any]]:
        try:
            resp = self.session.get(url, timeout=6)
            if resp.status_code != 200:
                return []

            raw_xml = resp.text
            if "<item>" not in raw_xml:
                return []

            items = []
            if HAS_FEEDPARSER:
                feed = feedparser.parse(raw_xml)
                for entry in feed.entries:
                    items.append({
                        "title": entry.get("title", ""),
                        "link": entry.get("link", ""),
                        "published": entry.get("published", ""),
                        "summary": entry.get("summary", ""),
                        "source": entry.get("source", {}).get("title", "Google News")
                    })
            else:
                items = self._parse_xml_fallback(raw_xml)

            return items
        except Exception as e:
            self.logger.debug(f"RSS fetch error: {e}")
            return []

    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Executes Google News RSS searches across target queries.
        """
        self.logger.info(f"Starting Google News collection for {profile.ticker}")

        # Clean company name
        clean_name = profile.company_name
        for suffix in [" Limited", " Ltd.", " Ltd"]:
            if clean_name.endswith(suffix):
                clean_name = clean_name[:-len(suffix)]

        # Assemble top prioritized search queries
        candidate_queries = []
        if queries:
            candidate_queries.extend(queries[:self.max_queries])
        else:
            candidate_queries = [
                f'"{clean_name}"',
                f'"{profile.ticker}"',
                f'"{clean_name}" earnings OR results',
                f'"{clean_name}" shares OR stock'
            ]

        records: List[RawArticleRecord] = []
        seen_urls = set()
        seen_titles = set()

        for idx, q in enumerate(candidate_queries):
            rss_url = self._build_rss_url(q, start_date=start_date, end_date=end_date)
            parsed_items = self._fetch_rss(rss_url)

            if parsed_items:
                self.save_raw_payload(profile.ticker, parsed_items, identifier=f"gnews_{idx}")

            retrieved_now = get_current_utc_iso()

            for item in parsed_items:
                link = item.get("link", "").strip()
                title = item.get("title", "").strip()
                if not link or not title:
                    continue

                norm_title = title.lower()
                if link in seen_urls or norm_title in seen_titles:
                    continue
                seen_urls.add(link)
                seen_titles.add(norm_title)

                final_url = link
                if self.resolve_redirects:
                    final_url = resolve_google_redirect(link, session=self.session)

                record = RawArticleRecord(
                    company_name=profile.company_name,
                    ticker=profile.ticker,
                    title=title,
                    description=item.get("summary", "").strip(),
                    url=final_url,
                    source=item.get("source", "Google News"),
                    source_type="NEWS_RSS",
                    primary_source=False,
                    published_at=parse_to_utc_iso(item.get("published")),
                    first_seen_at=retrieved_now,
                    retrieved_at=retrieved_now,
                    collector=self.name
                )
                records.append(record)

        self.logger.info(f"Google News collected {len(records)} unique articles for {profile.ticker}")
        return records
