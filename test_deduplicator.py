"""Beginner-level checks for deduplicator.py. Run: python -m unittest -v"""

import unittest

from deduplicator import deduplicate_articles, normalized_title, normalized_url


class DeduplicatorTests(unittest.TestCase):
    def test_tracking_query_does_not_change_url_identity(self):
        self.assertEqual(
            normalized_url("https://EXAMPLE.com/story/?utm_source=x"),
            normalized_url("https://example.com/story"),
        )

    def test_title_comparison_ignores_case_and_punctuation(self):
        self.assertEqual(normalized_title("Profit rises 12%!"), normalized_title("PROFIT rises 12"))

    def test_same_url_records_merge_but_keep_original_and_member_fields(self):
        records = [
            {"title": "Quarterly results", "url": "https://news.test/a?utm_source=x", "source": "A", "score": 8},
            {"title": "Results update", "url": "https://news.test/a", "source": "B", "score": 7},
        ]
        result = deduplicate_articles(records)
        self.assertEqual(result["record_count"], 1)
        self.assertEqual(result["input_record_count"], 2)
        self.assertEqual(result["articles"][0]["score"], 8)
        self.assertEqual(result["articles"][0]["duplicate_records"][0]["score"], 7)
        self.assertEqual(result["articles"][0]["deduplication"]["matched_by"], "url")
        self.assertTrue(result["articles"][0]["duplicate_cluster_id"].startswith("CLUSTER_"))

    def test_similar_but_distinct_titles_are_not_merged(self):
        records = [
            {"title": "Reliance profit rises 12 percent", "url": "https://a.test/1"},
            {"title": "Reliance profit rises 13 percent", "url": "https://b.test/2"},
        ]
        self.assertEqual(deduplicate_articles(records)["record_count"], 2)

    def test_exact_news_copies_count_as_one_possible_syndicated_evidence(self):
        records = [
            {"title": "Results", "url": "https://a.test/story", "source": "A", "source_type": "NEWS_RSS"},
            {"title": "Results", "url": "https://b.test/story", "source": "B", "source_type": "AGGREGATOR"},
        ]
        note = deduplicate_articles(records)["articles"][0]["deduplication"]["source_independence"]
        self.assertEqual(note["status"], "possible_syndication")
        self.assertEqual(note["independent_evidence_count"], 1)


if __name__ == "__main__":
    unittest.main()
