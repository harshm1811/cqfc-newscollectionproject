"""Group 2 pipeline handoff tests using synthetic records and temporary files."""

import json

import group2_pipeline


def test_pipeline_runs_semantic_deduplication_with_configurable_threshold(tmp_path, monkeypatch):
    seen = {}

    class StubSemanticDeduplicator:
        def __init__(self, *, similarity_threshold):
            seen["threshold"] = similarity_threshold
            self.model = type("Backend", (), {"backend": "test_stub"})()

        def cluster_articles(self, articles):
            for article in articles:
                article["duplicate_cluster_id"] = "synthetic-semantic-cluster"
                article["independent_source"] = True
            return articles

    monkeypatch.setattr(group2_pipeline, "SemanticDeduplicator", StubSemanticDeduplicator)
    source = "Synthetic test publisher"
    raw_records = [
        {
            "ticker": "TEST", "company_name": "Synthetic Test Company",
            "title": f"Synthetic test report {index}",
            "description": "Synthetic fixture text for pipeline testing only.",
            "url": f"https://publisher.example.test/{index}", "source": source,
            "source_type": "NEWS_RSS", "primary_source": False,
            "published_at": "2026-01-02T10:00:00Z",
            "first_seen_at": "2026-01-02T10:01:00Z",
            "retrieved_at": "2026-01-02T10:01:00Z",
        }
        for index in (1, 2)
    ]
    input_path = tmp_path / "synthetic-raw.json"
    output_path = tmp_path / "synthetic-processed.json"
    input_path.write_text(json.dumps(raw_records), encoding="utf-8")

    result = group2_pipeline.run_pipeline(
        input_path, output_path, semantic_similarity_threshold=0.72
    )

    assert seen["threshold"] == 0.72
    assert result["embedding_backend"] == "test_stub"
    assert "semantic_deduplication" in result["pipeline_steps"]
    assert {row["duplicate_cluster_id"] for row in result["articles"]} == {
        "synthetic-semantic-cluster"
    }
    assert result["semantic_cluster_count"] == 1
    assert json.loads(output_path.read_text(encoding="utf-8"))["record_count"] == 2
