"""Unit tests for processing/cleaner.py and processing/normalizer.py."""

from datetime import datetime, timezone
import unittest

from processing.cleaner import clean_article_text, clean_text, deduplicate_paragraphs, remove_boilerplate
from processing.normalizer import (
    normalize_article,
    normalize_articles,
    normalize_publisher,
    normalize_timestamp,
    normalize_url,
)


class TestCleaningAndNormalization(unittest.TestCase):
    def test_clean_text_strips_html_and_collapses_whitespace(self):
        dirty = "<p>Reliance   profit <b>rises</b> 16% &amp; beats estimates.</p>"
        cleaned = clean_text(dirty)
        self.assertEqual(cleaned, "Reliance profit rises 16% & beats estimates.")

    def test_deduplicate_paragraphs(self):
        text = "Paragraph one.\n\nParagraph two.\n\nParagraph one.\n\nParagraph three."
        deduped = deduplicate_paragraphs(text)
        expected = "Paragraph one.\n\nParagraph two.\n\nParagraph three."
        self.assertEqual(deduped, expected)

    def test_remove_boilerplate(self):
        text = "RIL announces new energy investment.\nSubscribe to our newsletter for more updates.\nAll rights reserved."
        clean = remove_boilerplate(text)
        self.assertEqual(clean, "RIL announces new energy investment.")

    def test_normalize_url_strips_tracking_parameters(self):
        url = "https://WWW.LiveMint.COM/companies/news/ril-q2?utm_source=twitter&utm_medium=social&gclid=12345&id=99"
        norm = normalize_url(url)
        self.assertEqual(norm, "https://livemint.com/companies/news/ril-q2?id=99")

    def test_normalize_timestamp_formats_iso_utc(self):
        # String parsing
        ts1 = "2025-10-20 15:30:00+05:30"
        norm1 = normalize_timestamp(ts1)
        self.assertEqual(norm1, "2025-10-20T10:00:00Z")

        # Datetime parsing
        dt = datetime(2025, 10, 20, 10, 0, 0, tzinfo=timezone.utc)
        self.assertEqual(normalize_timestamp(dt), "2025-10-20T10:00:00Z")

    def test_never_invent_missing_timestamps(self):
        self.assertIsNone(normalize_timestamp(None))
        self.assertIsNone(normalize_timestamp(""))
        self.assertIsNone(normalize_timestamp("invalid_date_format_string"))

    def test_normalize_publisher(self):
        self.assertEqual(normalize_publisher("livemint.com"), "Mint")
        self.assertEqual(normalize_publisher("economictimes"), "Economic Times")
        self.assertEqual(normalize_publisher("", "https://www.reuters.com/business"), "Reuters")

    def test_clean_article_text_preserves_original_record(self):
        raw = {
            "title": "Reliance Q2 Results",
            "description": "Consolidated net profit beats estimates.",
            "source": "BSE",
        }
        res = clean_article_text(raw)
        self.assertIn("original_record", res)
        self.assertEqual(res["clean_text"], "Reliance Q2 Results. Consolidated net profit beats estimates.")
        self.assertEqual(res["text_scope"], "title_and_description")

    def test_secondary_publisher_name_does_not_promote_provenance(self):
        for publisher in ("BSE News Desk", "SEBI Watch", "NSE Coverage"):
            with self.subTest(publisher=publisher):
                record = normalize_article({
                    "ticker": "TEST",
                    "company_name": "Synthetic Test Company",
                    "title": "Synthetic fixture headline",
                    "description": "Synthetic test-only description",
                    "url": "https://publisher.example.test/story",
                    "source": publisher,
                    "source_type": "NEWS_RSS",
                    "primary_source": False,
                })
                self.assertFalse(record["primary_source"])
                self.assertEqual(record["source_type"], "NEWS_RSS")

    def test_explicit_primary_company_ir_provenance_is_preserved(self):
        record = normalize_article({
            "ticker": "TEST",
            "company_name": "Synthetic Test Company",
            "title": "Synthetic test release",
            "description": "Synthetic test-only description",
            "url": "https://ir.example.test/release",
            "source": "Synthetic Test Company Investor Relations",
            "source_type": "COMPANY_IR",
            "primary_source": True,
        })
        self.assertTrue(record["primary_source"])
        self.assertEqual(record["source_type"], "COMPANY_IR")

    def test_string_false_is_not_truthy_primary_provenance(self):
        record = normalize_article({
            "ticker": "TEST",
            "company_name": "Synthetic Test Company",
            "title": "Synthetic fixture headline",
            "url": "https://bse.example.test/coverage",
            "source": "BSE coverage",
            "source_type": "NEWS_RSS",
            "primary_source": "false",
        })
        self.assertFalse(record["primary_source"])


if __name__ == "__main__":
    unittest.main()
