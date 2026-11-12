"""Small, dependency-free helpers for cleaning article text."""

from html.parser import HTMLParser
import re


class _TextExtractor(HTMLParser):
    """Extract readable text while ignoring scripts and styles."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts = []
        self.ignored_tags = []

    def handle_starttag(self, tag, attrs):
        if tag.lower() in {"script", "style"}:
            self.ignored_tags.append(tag.lower())

    def handle_endtag(self, tag):
        if self.ignored_tags and tag.lower() == self.ignored_tags[-1]:
            self.ignored_tags.pop()

    def handle_data(self, data):
        if not self.ignored_tags:
            self.parts.append(data)


def clean_text(value):
    """Remove HTML markup and repeated whitespace from a text value.

    Non-string values, including None, are returned unchanged so missing data
    is not silently turned into text.
    """
    if not isinstance(value, str):
        return value

    parser = _TextExtractor()
    try:
        parser.feed(value)
        parser.close()
        text = " ".join(parser.parts)
    except Exception:
        # Keep malformed markup safe and readable without failing the record.
        text = re.sub(r"<[^>]*>", " ", value)

    return " ".join(text.split())


def clean_article_text(article):
    """Return a copied article with common text fields cleaned."""
    cleaned = dict(article)
    for field in ("company_name", "ticker", "title", "description", "content", "summary", "source", "source_type", "collector"):
        if field in cleaned:
            cleaned[field] = clean_text(cleaned[field])

    # Group 1 currently supplies title and description, not the full body.
    # Keep an existing article text field when present; otherwise combine the
    # available title and description without claiming it is full text.
    body = cleaned.get("content") or cleaned.get("summary") or cleaned.get("description")
    pieces = [cleaned.get("title"), body]
    cleaned["clean_text"] = " ".join(value for value in pieces if isinstance(value, str) and value.strip())
    cleaned["text_scope"] = "article_body" if cleaned.get("content") else (
        "summary" if cleaned.get("summary") else "title_and_description"
    )
    return cleaned
