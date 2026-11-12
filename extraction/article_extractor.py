"""
extraction/article_extractor.py - Robust web and feed article extractor.

Extracts headline, description, article body text, author, publisher, and timestamp.
Supports graceful degradation with standard statuses:
SUCCESS, PARTIAL, METADATA_ONLY, BLOCKED, PAYWALLED, FAILED.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import logging
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup

from .metadata_extractor import MetadataExtractor

logger = logging.getLogger("group2.extraction")


class ExtractionStatus(str, Enum):
    SUCCESS = "SUCCESS"
    PARTIAL = "PARTIAL"
    METADATA_ONLY = "METADATA_ONLY"
    BLOCKED = "BLOCKED"
    PAYWALLED = "PAYWALLED"
    FAILED = "FAILED"


@dataclass
class ExtractionResult:
    status: ExtractionStatus
    title: Optional[str] = None
    description: Optional[str] = None
    article_text: Optional[str] = None
    author: Optional[str] = None
    publisher: Optional[str] = None
    published_at: Optional[str] = None
    canonical_url: Optional[str] = None
    error_message: Optional[str] = None
    raw_html: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "status": self.status.value,
            "title": self.title,
            "description": self.description,
            "article_text": self.article_text,
            "author": self.author,
            "publisher": self.publisher,
            "published_at": self.published_at,
            "canonical_url": self.canonical_url,
            "error_message": self.error_message,
        }


PAYWALL_INDICATORS = [
    "subscribe to read",
    "premium article",
    "subscriber-only",
    "exclusive for subscribers",
    "this article is for subscribers",
    "paywall",
    "join now to read",
]


class ArticleExtractor:
    """Extracts articles from HTML strings or via network requests."""

    def __init__(self, timeout: int = 10, user_agent: Optional[str] = None):
        self.timeout = timeout
        self.user_agent = user_agent or "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"

    def extract_from_html(self, html: str, base_url: str = "") -> ExtractionResult:
        """Parse HTML string into an ExtractionResult."""
        if not html or not html.strip():
            return ExtractionResult(status=ExtractionStatus.FAILED, error_message="Empty HTML content")

        # Check for paywalls
        html_lower = html.lower()
        if any(term in html_lower for term in PAYWALL_INDICATORS):
            # Still extract whatever metadata is available
            meta = MetadataExtractor.extract_from_html(html, base_url)
            return ExtractionResult(
                status=ExtractionStatus.PAYWALLED,
                title=meta.get("title"),
                description=meta.get("description"),
                publisher=meta.get("publisher"),
                published_at=meta.get("published_at"),
                canonical_url=meta.get("canonical_url"),
                raw_html=html,
            )

        try:
            soup = BeautifulSoup(html, "html.parser")
            meta = MetadataExtractor.extract_from_html(html, base_url)

            # Strip non-content elements
            for tag in soup(["script", "style", "nav", "header", "footer", "aside", "form"]):
                tag.decompose()

            # Attempt to find main article body
            article_node = (
                soup.find("article")
                or soup.find("main")
                or soup.find("div", class_=re.compile(r"article[-_]body|story[-_]content|entry[-_]content|post[-_]content", re.I))
            )

            target = article_node if article_node else soup.body
            paragraphs = []
            if target:
                for p in target.find_all("p"):
                    txt = p.get_text(strip=True)
                    if len(txt) > 20:
                        paragraphs.append(txt)

            article_text = "\n\n".join(paragraphs).strip() if paragraphs else None

            # Determine status
            title = meta.get("title")
            desc = meta.get("description")

            if article_text and len(article_text) >= 150:
                status = ExtractionStatus.SUCCESS
            elif article_text and len(article_text) > 0:
                status = ExtractionStatus.PARTIAL
            elif title or desc:
                status = ExtractionStatus.METADATA_ONLY
            else:
                status = ExtractionStatus.FAILED

            return ExtractionResult(
                status=status,
                title=title,
                description=desc,
                article_text=article_text,
                author=meta.get("author"),
                publisher=meta.get("publisher"),
                published_at=meta.get("published_at"),
                canonical_url=meta.get("canonical_url"),
                raw_html=html,
            )
        except Exception as e:
            logger.error(f"Error parsing HTML: {e}")
            return ExtractionResult(
                status=ExtractionStatus.FAILED,
                error_message=str(e),
                raw_html=html,
            )

    def extract_from_record(self, raw_record: Dict[str, Any], fetch_network: bool = False) -> ExtractionResult:
        """
        Process a candidate article record from Group 1.
        Never crashes; degrades gracefully to METADATA_ONLY if offline or fetch fails.
        """
        url = raw_record.get("url", "")
        existing_title = raw_record.get("title")
        existing_desc = raw_record.get("description")
        existing_content = raw_record.get("content")

        if existing_content and len(str(existing_content).strip()) > 100:
            return ExtractionResult(
                status=ExtractionStatus.SUCCESS,
                title=existing_title,
                description=existing_desc,
                article_text=str(existing_content).strip(),
                publisher=raw_record.get("source"),
                published_at=raw_record.get("published_at"),
                canonical_url=url,
            )

        if fetch_network and url and url.startswith("http"):
            try:
                import requests
                headers = {"User-Agent": self.user_agent}
                resp = requests.get(url, headers=headers, timeout=self.timeout)
                if resp.status_code == 200:
                    res = self.extract_from_html(resp.text, base_url=url)
                    if not res.title:
                        res.title = existing_title
                    if not res.description:
                        res.description = existing_desc
                    return res
                elif resp.status_code in (401, 403):
                    return ExtractionResult(
                        status=ExtractionStatus.BLOCKED,
                        title=existing_title,
                        description=existing_desc,
                        error_message=f"HTTP {resp.status_code} Blocked",
                    )
            except Exception as e:
                logger.warning(f"Network extraction failed for {url}: {e}")

        # Graceful fallback to feed metadata
        return ExtractionResult(
            status=ExtractionStatus.METADATA_ONLY if (existing_title or existing_desc) else ExtractionStatus.FAILED,
            title=existing_title,
            description=existing_desc,
            article_text=existing_content or existing_desc or "",
            publisher=raw_record.get("source"),
            published_at=raw_record.get("published_at"),
            canonical_url=url,
        )
