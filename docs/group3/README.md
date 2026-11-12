# Group 3 Event Intelligence

Group 3 accepts Group 2 article dictionaries and produces event records, article/event mappings, sentiment and importance values, and daily feature data. The integration entry point is `group3_pipeline.run_group3_pipeline(articles)`; `run_demo.py` is an offline demo runner.

## Interface

The pipeline accepts `article_id`, `ticker`, `company_name`, `title`, `clean_text`, source metadata, timestamps, relevance, and duplicate-cluster metadata. It returns `event_records` and a pandas `daily_features` DataFrame. Event records use `event_type`, `event_timestamp`, `sentiment_score`, positive/neutral/negative probabilities, importance metadata, `article_count`, `publisher_count`, and `primary_source_present`; the Group 4 adapter maps these names to the storage schema.

The default classifier and lexicon sentiment implementation run locally. FinBERT is optional and is used only when its transformer dependencies and model are available; otherwise the code falls back to lexicon sentiment. The dependency set intentionally does not download model weights.

`data/mock/mock_group2_articles.json` and the Group 3 tests contain synthetic examples only. They are not actual market data and must not be treated as application records.

Run the complete project checks with `python -m pytest -q` from the repository root.

## FinBERT configuration

FinBERT (`ProsusAI/finbert`) is the default sentiment model. Install `transformers` and `torch` from the root `requirements.txt`. On first use, model weights are downloaded to the local Hugging Face cache and are not stored in Git. When initialization or inference fails, the pipeline uses the lexicon model if fallback is enabled and reports the model and reason in its result. Set `SENTIMENT_MODEL=lexicon` for explicit lexicon scoring, `SENTIMENT_FALLBACK_ENABLED=false` to fail on FinBERT errors, and `SENTIMENT_DEVICE=-1` to force CPU. `scripts/verify_finbert.py` verifies real model inference when network access or cached weights are available.
