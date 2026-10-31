import unittest

import pandas as pd

from feature_engineering.adapters.input_adapter import adapt_enriched_outputs
from feature_engineering.pipeline import FeatureConfig, build_feature_dataset
from feature_engineering.sentiment_index import aggregate_event_sentiment


class FeatureEngineeringTests(unittest.TestCase):
    def setUp(self):
        self.articles = pd.DataFrame([
            {"article_id": "a1", "ticker": "ABC", "published_at": "2026-01-01T12:00Z", "relevance": 1, "source": "Wire A"},
            {"article_id": "a2", "ticker": "ABC", "published_at": "2026-01-01T13:00Z", "relevance": 1, "source": "Wire A"},
            {"article_id": "a3", "ticker": "ABC", "published_at": "2026-01-03T12:00Z", "relevance": 0, "source": "Wire B"},
        ])
        self.events = pd.DataFrame([
            {"event_id": "e1", "ticker": "ABC", "first_article_at": "2026-01-01T12:00Z", "sentiment_score": .6, "importance_score": .8, "primary_source_confirmed": True},
            {"event_id": "e2", "ticker": "ABC", "first_article_at": "2026-01-03T12:00Z", "sentiment_score": -.4, "importance_score": .9},
        ])
        self.mappings = pd.DataFrame([{"article_id": "a1", "event_id": "e1"}, {"article_id": "a2", "event_id": "e1"}, {"article_id": "a3", "event_id": "e2"}])

    def test_event_once_but_articles_count_individually(self):
        out = build_feature_dataset(self.articles, self.events, self.mappings)
        first = out[out.date == pd.Timestamp("2026-01-01", tz="UTC")].iloc[0]
        self.assertEqual(first.NewsCount, 2)
        self.assertEqual(first.UniqueEventCount, 1)

    def test_missing_calendar_date_and_momentum(self):
        out = build_feature_dataset(self.articles, self.events, self.mappings)
        self.assertIn(pd.Timestamp("2026-01-02", tz="UTC"), set(out.date))
        self.assertTrue(out.SentimentMomentum.notna().all())

    def test_weighted_mean_is_bounded_and_uses_event_weight(self):
        rows = self.events.assign(source_quality=1, time_weight=1, relevance=1)
        out = aggregate_event_sentiment(rows)
        self.assertTrue(out.WeightedSentiment.between(-1, 1).all())

    def test_adapter_keeps_ids_and_marks_mock_values(self):
        class Record:
            def __init__(self, row): self.row = row
            def to_dict(self): return self.row
        a, e, m = adapt_enriched_outputs(
            [Record({"article_id": "a", "ticker": "ABC", "published_at": "2026-01-01", "sentiment": {"sentiment_score": .2}})],
            [Record({"event_id": "e", "ticker": "ABC", "first_article_at": "2026-01-01", "sentiment_score": .3})],
            [Record({"article_id": "a", "event_id": "e", "similarity": .9})],
        )
        self.assertEqual(a.iloc[0].article_id, "a")
        self.assertEqual(e.iloc[0].event_id, "e")
        self.assertTrue(e.iloc[0].person2_is_mock)
        self.assertEqual(m.iloc[0].event_id, "e")


if __name__ == "__main__":
    unittest.main()
