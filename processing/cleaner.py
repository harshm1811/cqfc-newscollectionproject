"""
processing/cleaner.py - Production-ready text cleaning and boilerplate removal.

Removes:
- HTML markup and entities
- Navigation and footer text
- Advertisements and cookie messages
- Repeated publisher boilerplate
- Duplicate paragraphs
- Malformed characters and excess whitespace
- Tracking parameters
Preserves original raw content separately.
"""

from __future__ import annotations

import html
from html.parser import HTMLParser
import re
from typing import Any, Dict, List, Optional, Set

BOILERPLATE_PATTERNS = [
    r"follow us on (twitter|facebook|linkedin|instagram|telegram)",
    r"subscribe to our (newsletter|channel)",
    r"click here to (read|join|subscribe)",
    r"all rights reserved",
    r"copyright\s+\d{4}",
    r"terms of (service|use)",
    r"privacy policy",
    r"cookie policy",
    r"advertisement",
    r"sponsored content",
    r"read more:.*",
    r"also read:.*",
    r"share this article",
]

_BOILERPLATE_RE = re.compile(r"|".join(BOILERPLATE_PATTERNS), re.IGNORECASE)


class _HTMLTextExtractor(HTMLParser):
    """Extract readable text while stripping script, style, and comments."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts: List[str] = []
        self.ignored_tags: List[str] = []

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag.lower() in {"script", "style", "noscript", "svg"}:
            self.ignored_tags.append(tag.lower())

    def handle_endtag(self, tag: str) -> None:
        if self.ignored_tags and tag.lower() == self.ignored_tags[-1]:
            self.ignored_tags.pop()

    def handle_data(self, data: str) -> None:
        if not self.ignored_tags:
            self.parts.append(data)


def clean_text(value: Optional[str]) -> Optional[str]:
    """
    Remove HTML markup, malformed characters, and collapse excess whitespace.
    Returns non-strings unchanged to avoid inventing or distorting missing data.
    """
    if not isinstance(value, str):
        return value

    # 1. Parse HTML
    parser = _HTMLTextExtractor()
    try:
        parser.feed(value)
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        text = re.sub(r"<[^>]*>", " ", value)

    # 2. Decode entities and clean control/malformed characters
    text = html.unescape(text)
    text = re.sub(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f]", " ", text)

    # 3. Collapse whitespace
    lines = []
    for line in text.splitlines():
        cleaned_line = " ".join(line.split())
        if cleaned_line:
            lines.append(cleaned_line)

    return " ".join(lines)


def deduplicate_paragraphs(text: str) -> str:
    """Remove exact duplicate paragraphs while preserving order."""
    if not text or not isinstance(text, str):
        return text
    paragraphs = text.split("\n\n") if "\n\n" in text else text.splitlines()
    seen: Set[str] = set()
    unique = []
    for p in paragraphs:
        cleaned = " ".join(p.split())
        if not cleaned:
            continue
        key = cleaned.lower()
        if key not in seen:
            seen.add(key)
            unique.append(cleaned)
    return "\n\n".join(unique)


def remove_boilerplate(text: str) -> str:
    """Filter out standard disclaimers, cookie notices, and subscription promos."""
    if not text or not isinstance(text, str):
        return text
    lines = text.splitlines()
    kept = []
    for line in lines:
        stripped = line.strip()
        if not stripped:
            continue
        if _BOILERPLATE_RE.search(stripped):
            continue
        kept.append(stripped)
    return "\n".join(kept)


def clean_article_text(article: Dict[str, Any]) -> Dict[str, Any]:
    """
    Clean article text fields, remove duplicate paragraphs, strip boilerplate,
    and build canonical 'clean_text'.
    Preserves raw original input under 'original_record'.
    """
    cleaned = dict(article)
    if "original_record" not in cleaned:
        cleaned["original_record"] = dict(article)

    # Clean standard string fields
    for field in ("company_name", "ticker", "title", "description", "content", "summary", "source", "source_type", "collector"):
        if field in cleaned and cleaned[field]:
            cleaned[field] = clean_text(cleaned[field])

    # Combine available text for clean_text
    title = cleaned.get("title") or ""
    body = cleaned.get("content") or cleaned.get("article_text") or cleaned.get("summary") or cleaned.get("description") or ""

    if body:
        body = deduplicate_paragraphs(body)
        body = remove_boilerplate(body)
        body = clean_text(body)

    # If title is already in the beginning of body, don't duplicate it
    if body and title:
        if body.lower().startswith(title.lower()):
            clean_text_val = body
        else:
            clean_text_val = f"{title}. {body}"
    elif body:
        clean_text_val = body
    else:
        clean_text_val = title

    cleaned["clean_text"] = clean_text_val.strip()
    cleaned["text_scope"] = "article_body" if (cleaned.get("content") or cleaned.get("article_text")) else (
        "summary" if cleaned.get("summary") else "title_and_description"
    )
    return cleaned
