"""End-to-end checks for the Group 2 pipeline. Run: python -m unittest -v"""

import json
from pathlib import Path
import tempfile
import unittest

from pipeline import REQUIRED_OUTPUT_FIELDS, run_pipeline


class PipelineTests(unittest.TestCase):
    def test_mock_data_meets_required_schema(self):
        source = Path(__file__).with_name("mock_raw_articles.json")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "final.json"
            result = run_pipeline(source, output)

        self.assertEqual(result["input_record_count"], 5)
        self.assertEqual(result["record_count"], 5)
        for article in result["articles"]:
            self.assertTrue(set(REQUIRED_OUTPUT_FIELDS).issubset(article))
            self.assertGreaterEqual(article["relevance_score"], 0)
            self.assertLessEqual(article["relevance_score"], 1)
            self.assertTrue(article["clean_text"].startswith(article["title"]))
            self.assertTrue(article["article_id"])
            self.assertTrue(article["duplicate_cluster_id"])
        self.assertTrue(all(item["text_scope"] == "title_and_description" for item in result["articles"]))

    def test_ids_are_stable_between_runs(self):
        source = Path(__file__).with_name("mock_raw_articles.json")
        with tempfile.TemporaryDirectory() as folder:
            output = Path(folder) / "final.json"
            first = run_pipeline(source, output)
            second = run_pipeline(source, output)

        first_ids = [(a["article_id"], a["duplicate_cluster_id"]) for a in first["articles"]]
        second_ids = [(a["article_id"], a["duplicate_cluster_id"]) for a in second["articles"]]
        self.assertEqual(first_ids, second_ids)


if __name__ == "__main__":
    unittest.main()
