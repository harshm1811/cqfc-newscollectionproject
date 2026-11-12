"""
extraction/metadata_extractor.py - Extracts metadata from HTML tags or raw headers.
"""

from __future__ import annotations

import json
import re
from typing import Any, Dict, Optional
from bs4 import BeautifulSoup


class MetadataExtractor:
    """Extracts author, publisher, canonical URL, and publication timestamp from HTML."""

    @staticmethod
    def extract_from_html(html: str, base_url: str = "") -> Dict[str, Optional[str]]:
        """Extract headline, description, author, publisher, and timestamp from HTML."""
        meta: Dict[str, Optional[str]] = {
            "title": None,
            "description": None,
            "author": None,
            "publisher": None,
            "published_at": None,
            "canonical_url": None,
        }
        if not html or not isinstance(html, str):
            return meta

        try:
            soup = BeautifulSoup(html, "html.parser")
        except Exception:
            return meta

        # 1. Title / Headline
        og_title = soup.find("meta", property="og:title")
        tw_title = soup.find("meta", attrs={"name": "twitter:title"})
        title_tag = soup.find("title")
        if og_title and og_title.get("content"):
            meta["title"] = og_title["content"].strip()
        elif tw_title and tw_title.get("content"):
            meta["title"] = tw_title["content"].strip()
        elif title_tag and title_tag.string:
            meta["title"] = title_tag.string.strip()

        # 2. Description
        og_desc = soup.find("meta", property="og:description")
        meta_desc = soup.find("meta", attrs={"name": "description"})
        if og_desc and og_desc.get("content"):
            meta["description"] = og_desc["content"].strip()
        elif meta_desc and meta_desc.get("content"):
            meta["description"] = meta_desc["content"].strip()

        # 3. Author
        author_meta = (
            soup.find("meta", attrs={"name": "author"})
            or soup.find("meta", property="article:author")
            or soup.find("meta", attrs={"name": "byl"})
        )
        if author_meta and author_meta.get("content"):
            meta["author"] = author_meta["content"].strip()

        # 4. Publisher / Site name
        og_site = soup.find("meta", property="og:site_name")
        meta_pub = soup.find("meta", attrs={"name": "publisher"})
        if og_site and og_site.get("content"):
            meta["publisher"] = og_site["content"].strip()
        elif meta_pub and meta_pub.get("content"):
            meta["publisher"] = meta_pub["content"].strip()

        # 5. Published Time
        time_meta = (
            soup.find("meta", property="article:published_time")
            or soup.find("meta", property="og:published_time")
            or soup.find("meta", attrs={"name": "publication_date"})
            or soup.find("meta", attrs={"name": "date"})
        )
        if time_meta and time_meta.get("content"):
            meta["published_at"] = time_meta["content"].strip()

        # 6. Canonical URL
        canonical = soup.find("link", rel="canonical")
        if canonical and canonical.get("href"):
            meta["canonical_url"] = canonical["href"].strip()

        # 7. Check JSON-LD if published_at or author still missing
        if not meta["published_at"] or not meta["author"]:
            for script in soup.find_all("script", type="application/ld+json"):
                try:
                    if not script.string:
                        continue
                    data = json.loads(script.string)
                    if isinstance(data, list):
                        data = data[0] if data else {}
                    if isinstance(data, dict):
                        if not meta["published_at"] and "datePublished" in data:
                            meta["published_at"] = str(data["datePublished"])
                        if not meta["author"] and "author" in data:
                            auth = data["author"]
                            if isinstance(auth, dict):
                                meta["author"] = auth.get("name")
                            elif isinstance(auth, list) and auth:
                                meta["author"] = auth[0].get("name") if isinstance(auth[0], dict) else str(auth[0])
                            elif isinstance(auth, str):
                                meta["author"] = auth
                except Exception:
                    continue

        return meta
