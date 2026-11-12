# Group 2 news pipeline

## What it does

Reads Group 1 article JSON, cleans and normalizes records, calculates Member 2's equity relevance score, then runs Member 3's exact duplicate grouping and source-independence notes. The result keeps provenance fields and adds the agreed Group 2 → Group 3 fields:

`article_id`, `ticker`, `title`, `clean_text`, `source`, `source_type`, `published_at`, `first_seen_at`, `relevance_score`, and `duplicate_cluster_id`.

`clean_text` is assembled from text available in the input. For the supplied mock records, that means title plus description; it is not a full article body. `text_scope` records this limit.

## Run it

In a terminal opened in this folder:

```powershell
python pipeline.py mock_raw_articles.json final_articles.json
```

You can choose another JSON input/output path:

```powershell
python pipeline.py path\to\raw_articles.json path\to\group2_output.json
```

The input can be a JSON list of article objects or an object containing an `articles` list. The output contains a summary and the final `articles` list. Each duplicate group is represented once; original duplicate records are retained under `duplicate_records`.

## Run checks

```powershell
python -m unittest -v
```

The tests cover URL/title matching, conservative duplicate handling, required output fields, score ranges, and stable IDs.
