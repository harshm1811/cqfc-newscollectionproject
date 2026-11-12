# Equity News Intelligence & Sentiment Engine — Group 4

Repository: cqfc-newscollectionproject

Integrated implementation of the equity resolver and news collection, article processing, event/sentiment analysis, SQLite storage, run tracking, dashboard, reporting, and exports. It contains no seeded financial records. The end-to-end command uses configured public collectors and stores only records returned by those collectors; synthetic examples are isolated fixtures.

## Requirements and setup

- Python 3.13
- SQLite via Python's built-in `sqlite3`
- Streamlit, Pandas, Plotly, and Pytest (installed from `requirements.txt`)

PowerShell:

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

## Run the application

Initialize the database (safe to repeat), then start Streamlit. The Search page can run the full analysis for a company or ticker; it attempts extraction from up to 20 article pages by default and reports collection/extraction issues.

```powershell
python -c "from equity_news_engine.database import initialize_database; initialize_database()"
python -m streamlit run app.py
```

From the dashboard, set the equity and publication window in the sidebar, open **Search**, enter the company/ticker, and choose **GENERATE ANALYSIS**. The app stores the actual collected records and refreshes the selected equity. For CLI use, run `python run_intelligence.py Reliance`; add `--fetch-article-text` to attempt up to 20 page extractions.

The default database is `data/equity_news.db`. Set `EQUITY_NEWS_DB` to use another path. The dashboard initializes the schema when it starts and works when the database has no financial records.

The collection command accepts a company name, ticker, or supported alias. Add `--start-date` / `--end-date` to scope collection, `--semantic-similarity-threshold` to tune near-duplicate clustering, and `--fetch-article-text` to attempt bounded page extraction. Collector errors and unsupported sources are retained in the collection run. To verify the pipeline without network access, run `python run_demo.py` (synthetic demo input; it does not touch the application database).

Run tests:

```powershell
python -m pytest -q
```

## Architecture

- `app.py`: Streamlit entry point.
- `src/equity_news_engine/database/`: SQLite connection context, schema, initialization.
- `repository.py`: allowlisted CRUD, filters, relationships, and scoped sentiment retrieval. Dashboard and reporting code use this API instead of issuing SQL.
- `runs.py`: unique run IDs and lifecycle, configuration, collector/model metadata, counts, and failure tracking.
- `dashboard.py`: all eight pages, UI filters, charts, tables, and empty/error states.
- `reporting.py`: structured report, actual-record CSV/JSON export, and chart builders.
- `pipeline.py`: injectable adapters and sequential orchestration with audited stage failures.
- `group2_pipeline.py`: Group 1 candidate normalization, cleaning, relevance scoring, and duplicate grouping.
- `group3_pipeline.py`: article sentiment, event clustering/classification, importance, source quality, time decay, and daily feature generation.
- `src/equity_news_engine/integration.py`: concrete Group 1 → Group 2 → Group 3 → Group 4 adapters and repository persistence. `run_intelligence.py` is its CLI entry point.
- `tests/`: database, repository, tracking, pipeline, reporting, exports, and dashboard tests. Tests use temporary databases.

The test fixtures use explicitly synthetic `TEST` records in isolated temporary databases. They are only for verification and are not real financial data or seeded application data. The suite checks individual schema constraints and indexes, empty and populated dashboard states, report content, and CSV/JSON serialization of stored records.

## Database tables

1. `EQUITIES`: ticker, canonical company name, exchange, and country.
2. `SOURCES`: source identity, type, and primary-source flag.
3. `ARTICLES`: upstream article fields, timestamps, cleaning/relevance metadata, primary-source status, independent-source status, and source/equity references.
4. `EVENTS`: event identity, type, time, headline, sentiment, importance, publisher/independent-source counts, and primary-source confirmation.
5. `ARTICLE_EVENT_MAP`: many-to-many article/event links.
6. `SENTIMENT_RESULTS`: model/version, label, score, and probability JSON linked to an article or event.
7. `DAILY_FEATURES`: dated named numeric features per equity.
8. `COLLECTION_RUNS`: requested ticker/window, configuration, collectors, model versions, counts, status, and failure details.

Foreign keys are enabled on each connection. Score ranges, nonnegative counts, allowed run statuses, JSON fields, and link requirements have SQLite constraints. Indexes cover ticker/time lookups and common relationships. Timestamps are stored as ISO text; integrations should provide consistently formatted ISO-8601 values.

## Repository and run tracking

Use `Repository(db_path=None)` from `equity_news_engine.repository`. Public operations include `save`, `get`, `list_records`, `update`, `link_article_event`, `linked_articles`, `linked_events`, and `sentiment_records`. Table/column identifiers are allowlisted; values use parameterized queries. Invalid fields/JSON and SQLite failures raise `RepositoryError`.

`RunTracker.start(...)` creates a UUID run in `running` state. `finish(...)` records counts, end time and failures; a run with failures defaults to `partial_failure`. `fail(...)` preserves a stage and error detail while marking the run failed. Status values are `pending`, `running`, `succeeded`, `partial_failure`, and `failed`.

## Dashboard pages

- **Search**: run the full collection/analysis pipeline or inspect matching stored articles/events.
- **Overview**: company-scoped coverage counts, independent publishers, weighted and rolling sentiment, daily trends, event polarity, and recent run/failure status.
- **News Feed**: filtered stored articles.
- **Events**: stored events with type/importance charts and linked underlying article coverage.
- **Sentiment**: scoped model outputs with model selection and probability details.
- **Timeline**: dated article/event points.
- **Sources**: registered sources and source-type chart.
- **Export**: filtered article/event/feature tables, CSV and JSON downloads, structured JSON report.

All pages include appropriate empty states. Empty results do not cause placeholder financial content to appear.

## Reporting and export formats

`build_intelligence_report` returns JSON-serializable company scope, coverage, weighted sentiment trends, event breakdown, major positive/negative events, observed event-type themes, risk candidates, source analysis, run failures, and the underlying stored records. `records_for_export` supports `articles`, `events`, and `features`; `export_csv` and `export_json` handle empty and populated datasets. Export selection in the UI applies the active ticker and date filters.

## Pipeline and upstream integration

`run_intelligence.py` calls the Group 1 resolver/collectors, passes real candidate records through Group 2 and Group 3, then persists normalized articles, source identities, sentiment, event links, events, and daily features through the Group 4 repository. `PipelineOrchestrator` records each stage and `RunTracker` stores collection errors and output counts. Failures after earlier successful stages are recorded as partial failures. Re-running the same article/event updates those records rather than duplicating them.

The provisional minimum interface descriptions supplied for the project are:

- Group 1 → Group 2: ticker, company name, title, description, URL, source, source type, primary-source flag, published/first-seen/retrieved timestamps.
- Group 2 → Group 3: article ID, ticker, title, clean text, source/source type, published/first-seen timestamps, relevance score, duplicate cluster ID.
- Group 3 → Group 4: event ID, ticker, type, timestamp, headline, sentiment probabilities/score, importance, article/source counts.

The integration maps Group 1 publisher/provenance and timestamps into Group 2, Group 2 article IDs/text/relevance/deduplication into Group 3, and Group 3 event fields/probabilities/features into the Group 4 schema. Original Group 1 RSS/API payloads remain in the ignored `data/raw/` archive. The Group 4 schema does not store every upstream diagnostic field; see each group guide for retained-field limits. BSE collection remains unsupported until a verified BSE scrip-code mapping is configured. Company IR feeds require explicit per-ticker configuration.

## Known limitations

- The dashboard and collection pipeline do not perform Git or remote repository operations.
- Authentication, multi-user access, and deployment configuration are outside this local scope.
- The database schema is initialized with `CREATE TABLE IF NOT EXISTS`; it does not yet include versioned migrations for future schema changes.
- FinBERT is the default sentiment model. The lexicon model is used only when selected explicitly or when FinBERT fails and fallback is enabled; the selected model and fallback reason are retained in run metadata.
- Sentiment results without a linked article or event cannot be scoped by ticker/date in the dashboard.

## Group 1 collection module

The Group 1 equity resolver, query generator, collectors, and collection pipeline are retained at the repository root. They return raw candidate records with publisher/source identity, primary-source provenance, publication and capture timestamps, collector metadata, and structured collector status/errors. Google News fallback coverage is secondary reporting; BSE collection is explicitly unsupported when a verified six-digit scrip-code mapping is unavailable. Company investor-relations feeds require explicit per-ticker configuration. See [the Group 1 integration and usage notes](docs/group1/README.md). Group 1's standalone verification is `python run_tests.py`; the repository-wide suite is `python -m pytest -q`.

## Group 2 article processing

Group 2’s normalization, extraction, cleaning, relevance scoring, exact deduplication, and semantic near-duplicate clustering are wired into the production pipeline. The similarity threshold is configurable. SentenceTransformer embeddings are used when available; otherwise a deterministic local TF-IDF/character n-gram fallback runs offline. Its callable pipeline is `group2_pipeline.run_pipeline(input_path, output_path)`. Keep `final_articles.json` and other demonstration outputs out of the live database; `mock_raw_articles.json` is an explicitly synthetic fixture. See [Group 2 usage notes](docs/group2/README.md).

## Group 3 event intelligence

Group 3’s event clustering, classification, sentiment scoring, source quality, importance, time decay, and daily feature modules are available through `group3_pipeline.run_group3_pipeline(articles)`. It accepts Group 2’s processed `articles` and returns event records plus daily features. FinBERT is the default model; lexicon fallback is configurable. See [Group 3 usage notes](docs/group3/README.md). Group 2 and Group 3 mock files are synthetic test/demo inputs and are not application database seeds.

## Sentiment model configuration

Group 3 uses ProsusAI/FinBERT by default. Its `transformers` and `torch` dependencies are included in `requirements.txt`; model weights are downloaded into the local Hugging Face cache on first use and are not committed. If model initialization or inference fails, the pipeline records the fallback reason and uses the lexicon model when fallback is enabled. Set `SENTIMENT_MODEL=lexicon` to select lexicon sentiment explicitly, or set `SENTIMENT_FALLBACK_ENABLED=false` to fail instead of falling back. `SENTIMENT_DEVICE=-1` forces CPU inference. Model and fallback provenance are stored with collection run metadata.

The Group 3 demo reads synthetic examples from `data/mock/` and writes generated output beneath ignored `data/output/`; these are not live financial records. The production `run_intelligence.py` command uses actual configured collectors and persists only returned records.
