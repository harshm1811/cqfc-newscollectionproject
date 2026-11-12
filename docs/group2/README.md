# Group 2 Article Processing

Group 2 normalizes Group 1 candidate records, extracts available article text, cleans text, scores equity relevance, removes exact duplicates, and semantically clusters near-duplicate stories. The callable pipeline is `group2_pipeline.run_pipeline(input_path, output_path)`; it accepts a JSON list or an object with an `articles` list.

Example from the repository root:

```powershell
python group2_pipeline.py path\to\raw_articles.json path\to\processed_articles.json
```

The output contains an `articles` list with stable article IDs, `clean_text`, relevance scores, duplicate cluster IDs, and preserved source/timestamp provenance. `text_scope` reports whether text came only from title/description. Set `--semantic-similarity-threshold` (default `0.65`) to tune semantic clustering. The declared SentenceTransformers dependency loads `all-MiniLM-L6-v2` on first use; a deterministic TF-IDF/character n-gram model is the offline fallback. The dashboard's Generate Analysis action attempts network extraction for up to 20 URLs by default. The CLI leaves network extraction opt-in with `--fetch-article-text`; all extraction outcomes are recorded in the collection run.

Run the repository suite with `python -m pytest -q`. `mock_raw_articles.json` and `tests/fixtures/group2/mock_processed_articles.json` are synthetic examples for tests/demo only. They are not real financial records and are never inserted into the application database. CLI-generated `final_articles.json` is ignored by Git.
