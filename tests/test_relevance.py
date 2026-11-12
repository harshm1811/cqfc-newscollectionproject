"""Unit tests for processing/relevance.py."""

import unittest
from processing.relevance import RelevanceEngine, calculate_relevance_score


class TestRelevance(unittest.TestCase):
    def setUp(self):
        self.engine = RelevanceEngine(min_relevance_threshold=0.50)
        self.profile = {
            "name": "Reliance Industries Limited",
            "ticker": "RELIANCE",
            "aliases": ["Reliance Industries", "RIL", "Reliance"],
            "subsidiaries": ["Jio", "Jio Platforms", "Reliance Retail"],
        }

    def test_high_relevance_headline_financial_event(self):
        record = {
            "title": "Reliance reports 20% profit increase in Q2",
            "clean_text": "Reliance Industries Limited reported a 20% rise in quarterly net profit beating analyst forecasts.",
        }
        score = self.engine.score_record(record, self.profile)
        self.assertGreaterEqual(score, 0.90)

    def test_low_relevance_passing_mention(self):
        record = {
            "title": "Executives attend annual industry summit in New Delhi",
            "clean_text": "Executives from Reliance and several companies attended an industry conference on global manufacturing trends.",
        }
        score = self.engine.score_record(record, self.profile)
        self.assertLessEqual(score, 0.35)

    def test_subsidiary_mention_boosts_relevance(self):
        record = {
            "title": "Jio unveils enterprise 5G cloud AI platform",
            "clean_text": "Telecom operator Jio announced the nationwide rollout of new enterprise generative AI cloud services.",
        }
        score = self.engine.score_record(record, self.profile)
        self.assertGreaterEqual(score, 0.70)

    def test_configurable_threshold_filtering(self):
        articles = [
            {"title": "Reliance Q2 profit beats estimates", "clean_text": "RIL net profit jumps.", "ticker": "RELIANCE"},
            {"title": "Industry conference attended by delegates", "clean_text": "Many attended.", "ticker": "RELIANCE"},
        ]
        relevant, excluded = self.engine.filter_relevant(articles, threshold=0.50)
        self.assertEqual(len(relevant), 1)
        self.assertEqual(len(excluded), 1)
        self.assertIn("Reliance Q2 profit", relevant[0]["title"])


if __name__ == "__main__":
    unittest.main()
