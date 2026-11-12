"""Unit tests for exact and semantic deduplication."""

import unittest
from processing.exact_deduplicator import ExactDeduplicator, content_hash, normalized_title
from processing.semantic_deduplicator import SemanticDeduplicator


class TestDeduplication(unittest.TestCase):
    def setUp(self):
        self.exact_dedup = ExactDeduplicator()
        self.semantic_dedup = SemanticDeduplicator(similarity_threshold=0.60)

    def test_content_hash_deterministic(self):
        text1 = "Reliance profit rises 16% in Q2 results."
        text2 = "Reliance   profit rises  16% in Q2 results!"
        self.assertEqual(content_hash(text1), content_hash(text2))

    def test_exact_deduplication_by_url_and_title(self):
        articles = [
            {
                "title": "Reliance Q2 Profit Jumps 16%",
                "url": "https://mint.com/news/ril-q2?utm_source=twitter",
                "source": "Mint",
                "clean_text": "RIL net profit surged 16% in the second quarter.",
            },
            {
                "title": "Reliance Q2 Profit Jumps 16%!",
                "url": "https://mint.com/news/ril-q2",
                "source": "Mint",
                "clean_text": "RIL net profit surged 16% in the second quarter.",
            },
        ]
        res = self.exact_dedup.deduplicate(articles)
        self.assertEqual(res["record_count"], 1)
        self.assertEqual(res["input_record_count"], 2)
        self.assertEqual(res["duplicate_group_count"], 1)
        self.assertTrue(res["articles"][0]["duplicate_cluster_id"].startswith("CLUST-"))

    def test_semantic_clustering_near_duplicates(self):
        articles = [
            {
                "article_id": "ART-1",
                "ticker": "RELIANCE",
                "title": "Reliance quarterly profit beats estimates",
                "clean_text": "Reliance reported higher than expected quarterly net earnings.",
                "source": "Mint",
            },
            {
                "article_id": "ART-2",
                "ticker": "RELIANCE",
                "title": "RIL reports stronger-than-expected quarterly earnings",
                "clean_text": "Reliance quarterly net profit topped street estimates.",
                "source": "Reuters",
            },
            {
                "article_id": "ART-3",
                "ticker": "RELIANCE",
                "title": "Reliance earnings exceed analyst forecasts",
                "clean_text": "Reliance quarterly net profit topped street expectations.",
                "source": "Bloomberg",
            },
        ]
        clustered = self.semantic_dedup.cluster_articles(articles)
        cluster_ids = {a["duplicate_cluster_id"] for a in clustered}
        # All three describe the exact same event and should share a single cluster ID
        self.assertEqual(len(cluster_ids), 1)
        # All three are from distinct independent publishers
        self.assertTrue(all(a["independent_source"] for a in clustered))

    def test_syndicated_duplicate_publisher_independence(self):
        articles = [
            {
                "article_id": "ART-A",
                "ticker": "RELIANCE",
                "title": "Reliance announces major petrochemical investment",
                "clean_text": "Conglomerate announces capex for green hydrogen and chemicals.",
                "source": "Reuters",
            },
            {
                "article_id": "ART-B",
                "ticker": "RELIANCE",
                "title": "Reliance announces major petrochemical investment",
                "clean_text": "Conglomerate announces capex for green hydrogen and chemicals.",
                "source": "Reuters",  # Duplicate publication from same publisher
            },
        ]
        clustered = self.semantic_dedup.cluster_articles(articles)
        self.assertEqual(len(clustered), 2)
        # First publication is independent, second copy is marked non-independent
        self.assertTrue(clustered[0]["independent_source"])
        self.assertFalse(clustered[1]["independent_source"])


if __name__ == "__main__":
    unittest.main()
