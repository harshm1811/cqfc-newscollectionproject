# Group 2 Article Processing

Group 2 normalizes Group 1 candidate records, extracts available article text, cleans text, scores equity relevance, and groups duplicates. The callable pipeline is `group2_pipeline.run_pipeline(input_path, output_path)`; it accepts a JSON list or an object with an `articles` list.

Example from the repository root:

```powershell
python group2_pipeline.py path\to\raw_articles.json path\to\processed_articles.json
```

The output contains an `articles` list with stable article IDs, `clean_text`, relevance scores, duplicate cluster IDs, and preserved source/timestamp provenance. `text_scope` reports whether text came only from title/description. The standalone extractor supports network fetching, but the standard Group 2 processing pipeline does not fetch article pages; it uses text already present in each input record.

Run the repository suite with `python -m pytest -q`. `mock_raw_articles.json` and `tests/fixtures/group2/mock_processed_articles.json` are synthetic examples for tests/demo only. They are not real financial records and are never inserted into the application database. CLI-generated `final_articles.json` is ignored by Git.
