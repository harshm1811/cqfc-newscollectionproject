"""
company_ir_collector.py - Company Investor Relations & Press Release Collector

PRIMARY SOURCE COLLECTOR
source_type = "COMPANY_IR"
primary_source = True

Responsibilities:
- Targeted collector for official company press release feeds or media rooms.
- Configurable per company (e.g. Reliance Media Releases, TCS Press Releases).
"""

from typing import List, Optional, Dict, Any
from datetime import datetime
import xml.etree.ElementTree as ET

from .base_collector import BaseCollector, RawArticleRecord
from equity.profile import EquityProfile
from utils.http_client import create_http_session
from utils.timestamp_parser import get_current_utc_iso, parse_to_utc_iso

try:
    import feedparser
    HAS_FEEDPARSER = True
except ImportError:
    HAS_FEEDPARSER = False


class CompanyIRCollector(BaseCollector):
    """
    Collector for corporate press releases and IR announcements.
    """

    def __init__(self, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        super().__init__(name="company_ir", raw_data_dir=raw_data_dir, config=config)
        self.session = create_http_session()
        self.ir_cfg = (config or {}).get("collectors", {}).get("company_ir", {})

    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Fetches official corporate press releases.
        """
        self.logger.info(f"Company IR collection for {profile.company_name}")
        feeds_by_ticker = self.ir_cfg.get("feeds_by_ticker", {})
        feeds = feeds_by_ticker.get(profile.ticker, [])
        if not feeds:
            self.mark_unsupported(
                f"No company IR feed is configured for {profile.ticker}; no company site is guessed"
            )
            return []

        records: List[RawArticleRecord] = []
        for feed_spec in feeds:
            url = feed_spec.get("url")
            source_name = feed_spec.get("source") or feed_spec.get("name")
            if not url or not source_name:
                self.record_error("configuration", "Company IR feed requires both url and source/name")
                continue
            try:
                response = self.session.get(url, timeout=10)
                if response.status_code != 200:
                    self.record_error("company_ir_feed", f"HTTP {response.status_code} from {url}")
                    continue
                raw_xml = response.text
                self.save_raw_payload(profile.ticker, raw_xml, identifier="company_ir")
                items = []
                if HAS_FEEDPARSER:
                    parsed = feedparser.parse(raw_xml)
                    for entry in parsed.entries:
                        publisher = entry.get("source", {}).get("title") or source_name
                        items.append({
                            "title": entry.get("title") or "",
                            "link": entry.get("link") or "",
                            "summary": entry.get("summary") or "",
                            "published": entry.get("published") or "",
                            "source": publisher,
                        })
                else:
                    root = ET.fromstring(raw_xml)
                    for item in root.findall(".//item"):
                        items.append({
                            "title": item.findtext("title") or "",
                            "link": item.findtext("link") or "",
                            "summary": item.findtext("description") or "",
                            "published": item.findtext("pubDate") or "",
                            "source": (item.find("source").text if item.find("source") is not None else source_name),
                        })

                captured_at = get_current_utc_iso()
                for item in items:
                    if not item["title"] or not item["link"]:
                        continue
                    primary = bool(feed_spec.get("primary_source", False))
                    records.append(RawArticleRecord(
                        company_name=profile.company_name,
                        ticker=profile.ticker,
                        title=item["title"],
                        description=item["summary"],
                        url=item["link"],
                        source=item["source"],
                        source_type="COMPANY_IR" if primary else "AGGREGATOR",
                        primary_source=primary,
                        published_at=parse_to_utc_iso(item["published"]),
                        first_seen_at=captured_at,
                        retrieved_at=captured_at,
                        collector=self.name,
                        raw_url=item["link"],
                    ))
            except Exception as exc:
                self.record_error(f"feed:{source_name}", exc)
        return records
