"""Unit tests for extraction/article_extractor.py and metadata_extractor.py."""

import unittest
from extraction.article_extractor import ArticleExtractor, ExtractionStatus
from extraction.metadata_extractor import MetadataExtractor


class TestExtraction(unittest.TestCase):
    def setUp(self):
        self.extractor = ArticleExtractor()

    def test_metadata_extraction_from_html(self):
        sample_html = """
        <!DOCTYPE html>
        <html>
        <head>
            <title>Reliance Q2 Net Profit Jumps 16%</title>
            <meta property="og:title" content="Reliance Q2 Net Profit Jumps 16%" />
            <meta property="og:description" content="RIL reported strong earnings for the second quarter." />
            <meta name="author" content="Harsh Mishra" />
            <meta property="og:site_name" content="Mint" />
            <meta property="article:published_time" content="2025-10-20T10:00:00Z" />
            <link rel="canonical" href="https://livemint.com/market/ril-q2" />
        </head>
        <body>
            <article>
                <p>Reliance Industries Limited reported a strong second-quarter financial performance with net profit rising 16% year-on-year.</p>
                <p>The growth was driven by retail EBITDA expansion and digital services subscriber additions.</p>
            </article>
        </body>
        </html>
        """
        meta = MetadataExtractor.extract_from_html(sample_html)
        self.assertEqual(meta["title"], "Reliance Q2 Net Profit Jumps 16%")
        self.assertEqual(meta["author"], "Harsh Mishra")
        self.assertEqual(meta["publisher"], "Mint")
        self.assertEqual(meta["published_at"], "2025-10-20T10:00:00Z")
        self.assertEqual(meta["canonical_url"], "https://livemint.com/market/ril-q2")

    def test_article_extraction_success(self):
        sample_html = """
        <html><body>
            <article>
                <p>Reliance Industries Limited reported a strong second-quarter financial performance with consolidated net profit rising 16% year-on-year to Rs 19,324 crore.</p>
                <p>Oil-to-chemical revenue recovered alongside continuous momentum in the Jio telecom segment.</p>
            </article>
        </body></html>
        """
        result = self.extractor.extract_from_html(sample_html)
        self.assertIn(result.status, [ExtractionStatus.SUCCESS, ExtractionStatus.PARTIAL])
        self.assertIsNotNone(result.article_text)
        self.assertIn("19,324 crore", result.article_text)

    def test_paywall_detection(self):
        paywall_html = """
        <html><body>
            <h1>Exclusive News</h1>
            <p>This premium article is for subscribers only. Join now to read more.</p>
        </body></html>
        """
        result = self.extractor.extract_from_html(paywall_html)
        self.assertEqual(result.status, ExtractionStatus.PAYWALLED)

    def test_malformed_html_does_not_crash(self):
        malformed = "<html><body><article><p>Unclosed paragraph"
        result = self.extractor.extract_from_html(malformed)
        self.assertIsNotNone(result)

    def test_empty_html_fails_gracefully(self):
        result = self.extractor.extract_from_html("")
        self.assertEqual(result.status, ExtractionStatus.FAILED)

    def test_record_fallback_without_network(self):
        raw_record = {
            "title": "TCS bags $1B deal",
            "description": "Tata Consultancy Services won a major multi-year banking contract.",
            "url": "https://example.com/tcs-contract",
            "source": "BSE",
        }
        result = self.extractor.extract_from_record(raw_record, fetch_network=False)
        self.assertEqual(result.status, ExtractionStatus.METADATA_ONLY)
        self.assertEqual(result.title, "TCS bags $1B deal")


if __name__ == "__main__":
    unittest.main()
