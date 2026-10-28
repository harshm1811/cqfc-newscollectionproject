"""
google_news_rss.py - Google News RSS Collector (Person B)

Responsibilities:
- Builds Google News search RSS queries from profile & generated queries:
  https://news.google.com/rss/search?q={query}&hl=en-IN&gl=IN&ceid=IN:en
- Robust XML parsing using feedparser (with fallback to xml.etree.ElementTree).
- Normalizes published timestamps to ISO-8601 UTC.
- Saves raw unedited feed XML/JSON to data/raw/{ticker}/.
- Emits RawArticleRecord objects with source_type="NEWS_RSS", primary_source=False.
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import urllib.parse
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
    Collects financial articles via Google News RSS search.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="google_news_rss", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.gnews_cfg = (config or {}).get("collectors", {}).get("google_news_rss", {})
        self.hl = self.gnews_cfg.get("language", "en-IN")
        self.gl = self.gnews_cfg.get("country_code", "IN")
        self.resolve_redirects = self.gnews_cfg.get("resolve_redirect_urls", False)

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
            self.logger.warning(f"XML parse error in GoogleNewsRSSCollector: {e}")
        return items

    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Executes Google News RSS search across target queries.
        """
        self.logger.info(f"Starting Google News collection for {profile.ticker}")
        search_queries = queries[:6] if queries else [f'"{profile.company_name}"', f'"{profile.ticker}"']

        records: List[RawArticleRecord] = []
        seen_urls = set()

        for q in search_queries:
            rss_url = self._build_rss_url(q, start_date=start_date, end_date=end_date)
            try:
                resp = self.session.get(rss_url, timeout=10)
                if resp.status_code != 200:
                    self.logger.warning(f"Google News RSS HTTP {resp.status_code} for query: {q}")
                    continue

                raw_xml = resp.text
                self.save_raw_payload(profile.ticker, raw_xml, identifier="gnews_rss")

                # Parse items
                parsed_items = []
                if HAS_FEEDPARSER:
                    feed = feedparser.parse(raw_xml)
                    for entry in feed.entries:
                        parsed_items.append({
                            "title": entry.get("title", ""),
                            "link": entry.get("link", ""),
                            "published": entry.get("published", ""),
                            "summary": entry.get("summary", ""),
                            "source": entry.get("source", {}).get("title", "Google News")
                        })
                else:
                    parsed_items = self._parse_xml_fallback(raw_xml)

                retrieved_now = get_current_utc_iso()

                for item in parsed_items:
                    link = item.get("link", "")
                    if not link or link in seen_urls:
                        continue
                    seen_urls.add(link)

                    final_url = link
                    if self.resolve_redirects:
                        final_url = resolve_google_redirect(link, session=self.session)

                    record = RawArticleRecord(
                        company_name=profile.company_name,
                        ticker=profile.ticker,
                        title=item.get("title", "").strip(),
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

            except Exception as e:
                self.logger.error(f"Error fetching Google News for query '{q}': {e}")

        self.logger.info(f"Google News collected {len(records)} items for {profile.ticker}")
        return records
