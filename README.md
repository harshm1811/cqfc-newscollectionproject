# Equity News Intelligence & Sentiment Engine — Group 4

Repository: cqfc-newscollectionproject

Local implementation of Group 4's database, repository, run tracking, dashboard, reporting, export, and orchestration infrastructure. It contains no seeded financial records. Data displayed and exported comes from records supplied to the repository by an actual integration or by a user.

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

Initialize the database (safe to repeat), then start Streamlit:

```powershell
python -c "from equity_news_engine.database import initialize_database; initialize_database()"
python -m streamlit run app.py
```

The default database is `data/equity_news.db`. Set `EQUITY_NEWS_DB` to use another path. The dashboard initializes the schema when it starts and works when the database has no financial records.

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
- `tests/`: database, repository, tracking, pipeline, reporting, exports, and dashboard tests. Tests use temporary databases.

The test fixtures use explicitly synthetic `TEST` records in isolated temporary databases. They are only for verification and are not real financial data or seeded application data. The suite checks individual schema constraints and indexes, empty and populated dashboard states, report content, and CSV/JSON serialization of stored records.

## Database tables

1. `EQUITIES`: ticker and company name.
2. `SOURCES`: source identity, type, and primary-source flag.
3. `ARTICLES`: upstream article fields, timestamps, cleaning/relevance metadata, and source/equity references.
4. `EVENTS`: event identity, type, time, headline, sentiment, importance, and counts.
5. `ARTICLE_EVENT_MAP`: many-to-many article/event links.
6. `SENTIMENT_RESULTS`: model/version, label, score, and probability JSON linked to an article or event.
7. `DAILY_FEATURES`: dated named numeric features per equity.
8. `COLLECTION_RUNS`: requested ticker/window, configuration, collectors, model versions, counts, status, and failure details.

Foreign keys are enabled on each connection. Score ranges, nonnegative counts, allowed run statuses, JSON fields, and link requirements have SQLite constraints. Indexes cover ticker/time lookups and common relationships. Timestamps are stored as ISO text; integrations should provide consistently formatted ISO-8601 values.

## Repository and run tracking

Use `Repository(db_path=None)` from `equity_news_engine.repository`. Public operations include `save`, `get`, `list_records`, `update`, `link_article_event`, `linked_articles`, `linked_events`, and `sentiment_records`. Table/column identifiers are allowlisted; values use parameterized queries. Invalid fields/JSON and SQLite failures raise `RepositoryError`.

`RunTracker.start(...)` creates a UUID run in `running` state. `finish(...)` records counts, end time and failures; a run with failures defaults to `partial_failure`. `fail(...)` preserves a stage and error detail while marking the run failed. Status values are `pending`, `running`, `succeeded`, `partial_failure`, and `failed`.

## Dashboard pages

- **Search**: search existing ticker records and inspect matching articles/events.
- **Overview**: actual record counts, news volume, sentiment, event types, and importance.
- **News Feed**: filtered stored articles.
- **Events**: stored events with type and importance charts.
- **Sentiment**: scoped sentiment records and label chart.
- **Timeline**: dated article/event points.
- **Sources**: registered sources and source-type chart.
- **Export**: filtered article/event/feature tables, CSV and JSON downloads, structured JSON report.

All pages include appropriate empty states. Empty results do not cause placeholder financial content to appear.

## Reporting and export formats

`build_intelligence_report` returns JSON-serializable scope, generation time, data status, counts, and actual article/event/feature/sentiment/source records. `records_for_export` supports `articles`, `events`, and `features`; `export_csv` and `export_json` handle empty and populated datasets. Export selection in the UI applies the active ticker and date filters.

## Pipeline and upstream integration

`PipelineOrchestrator` executes the required Group 1 → Group 2 → Group 3 → Group 4 order. `Group1Adapter`, `Group2Adapter`, `Group3Adapter`, and `Group4Adapter` accept real callbacks. Missing callbacks raise `AdapterUnavailable`, stop downstream execution, and are recorded in the run. Earlier successful stages produce `partial_failure`; failure at the first stage is `failed`. Payloads are passed through without invented field conversions. The Group 4 persistence callback must map confirmed upstream records to repository saves.

The provisional minimum interface descriptions supplied for the project are:

- Group 1 → Group 2: ticker, company name, title, description, URL, source, source type, primary-source flag, published/first-seen/retrieved timestamps.
- Group 2 → Group 3: article ID, ticker, title, clean text, source/source type, published/first-seen timestamps, relevance score, duplicate cluster ID.
- Group 3 → Group 4: event ID, ticker, type, timestamp, headline, sentiment probabilities/score, importance, article/source counts.

These are integration notes, not finalized contracts. Group 1/2 source identity and Group 3 probability encoding/field names still need agreement. No real upstream code is currently connected. Before connecting it, confirm identifiers, nullability, timestamp formats, score scales, probability representation, and failure semantics with the relevant group. Group 4's schema accepts the minimum listed event concepts but does not infer or calculate upstream results.

## Known limitations

- The project is local only; no Git or remote operations are used.
- Authentication, multi-user access, and deployment configuration are outside this local scope.
- The database schema is initialized with `CREATE TABLE IF NOT EXISTS`; it does not yet include versioned migrations for future schema changes.
- Pipeline callbacks and final Group 4 record mapping await confirmed Group 1–3 implementations and finalized contracts.
- Sentiment results without a linked article or event cannot be scoped by ticker/date in the dashboard.
