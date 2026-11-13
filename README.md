# Equity News Intelligence & Sentiment Engine

An end-to-end, free, and modular equity news intelligence platform. The system ingests public financial news and primary-source regulatory filings, cleans and filters noise, clusters stories into distinct financial events, scores sentiment using financial NLP (FinBERT), calculates point-in-time quantitative features, and presents insights through an interactive Streamlit dashboard, structured intelligence reports, and CSV/JSON datasets.

---

## Four-Group Project Division & Architecture

The system is divided into four largely independent subsystems with standardized interfaces:

```
                  GROUP 1: EQUITY RESOLUTION & NEWS COLLECTION
                      User Query ──► Raw Candidate News Records
                                      │
                                      ▼
             GROUP 2: EXTRACTION, CLEANING, RELEVANCE & DEDUPLICATION
                     Raw News ──► Clean, Unique, Relevant Articles
                                      │
                                      ▼
               GROUP 3: EVENT INTELLIGENCE, SENTIMENT & QUANT FEATURES
                     Clean Articles ──► Events + Daily Quant Features
                                      │
                                      ▼
              GROUP 4: DATABASE, REPORTING, DASHBOARD & INTEGRATION
                  SQLite Storage + Streamlit UI + Reports + Orchestration
```

### Subsystem Responsibilities

1. **Group 1 — Equity Resolution & News Collection**
   * **Equity Resolver**: Resolves Indian equities from the local NSE listing and can look up international listed equities using Yahoo Finance's public symbol search. Local NSE lookup supports aliases and typo-tolerant matching; international lookup requires an exact ticker or company-name match.
   * **Query Generator**: Generates targeted financial search queries across 37+ categories (earnings, M&A, capex, litigation, dividends, etc.).
   * **Public Collectors**: Discovers news and announcements from Google News RSS, exchange feeds (NSE, BSE with scrip codes), regulatory releases (SEBI), and company IR pages.
   * **Provenance & Timestamps**: Strictly tags primary sources and captures point-in-time timestamps (`published_at`, `first_seen_at`, `retrieved_at`) without date invention.

2. **Group 2 — Extraction, Cleaning, Relevance & Deduplication**
   * **Article & Metadata Extraction**: Extracts headline, body text, author, publisher, and timestamps with graceful status tracking (`SUCCESS`, `PARTIAL`, `METADATA_ONLY`, `BLOCKED`, `PAYWALLED`, `FAILED`).
   * **Cleaning & Normalization**: Strips HTML, navigation text, boilerplate, ads, and duplicate paragraphs. Canonicalizes URLs (stripping tracking parameters), maps publisher aliases, and normalizes timestamps to UTC ISO-8601.
   * **Relevance Engine**: Evaluates company name frequency, headline mentions, ticker occurrence, subsidiaries, and financial action keywords to compute a configurable equity relevance score $\in [0, 1]$.
   * **Exact & Semantic Deduplication**: Groups identical stories via URL, title, and content hashing. Clusters near-duplicate and reworded stories using sentence embeddings (`SentenceTransformers` / `all-MiniLM-L6-v2` with a deterministic offline TF-IDF fallback). Tags source independence and primary sources.

3. **Group 3 — Event Intelligence, Sentiment & Quant Features**
   * **Financial Sentiment**: Local FinBERT (`ProsusAI/finbert`) scoring with an automatic, resilient lexicon fallback. Preserves positive, neutral, and negative probability distributions.
   * **Event Clustering & Classification**: Groups multi-source reporting into distinct financial events and classifies them into 20 financial event categories (Earnings, M&A, Capex, Buyback, Regulation, etc.).
   * **Event Importance & Source Quality**: Computes multi-factor importance scores, applies source quality weights, and calculates exponential time decay ($e^{-\lambda \cdot \text{age}}$).
   * **Daily Quantitative Features**: Generates point-in-time daily feature datasets suitable for OHLCV financial modeling (rolling sentiment windows 1D/3D/7D/30D, sentiment momentum, volume z-scores, positive/negative shocks, and dispersion).

4. **Group 4 — Database, Reporting, Dashboard & Integration**
   * **SQLite Database**: Production-grade schema (8 relational tables with foreign keys and audit constraints).
   * **Repository Layer**: Centralized, parameterized data access preventing raw SQL in business modules.
   * **Run Tracking**: Unique UUID run lifecycle management recording configuration, collector errors, and stage outputs.
   * **Streamlit Application**: Multi-page interactive analytics portal with 8 dedicated views.
   * **Report Generator & Exporter**: Generates structured equity intelligence reports and exports CSV/JSON datasets.
   * **Pipeline Orchestration**: Central orchestrator (`run_intelligence.py`) chaining Groups 1 $\rightarrow$ 2 $\rightarrow$ 3 $\rightarrow$ 4 with audited partial-failure handling.

---

## Requirements and Setup

- **Python**: Python 3.10 to 3.13 recommended (Python 3.14 compatible; PyTorch/Transformers require Python $\le$ 3.13 for prebuilt binary wheels).
- **Database**: SQLite via Python's built-in `sqlite3`.
- **Core Dependencies**: Streamlit, Pandas, Plotly, PyYAML, BeautifulSoup4, Requests, Python-Dateutil, and Pytest.
- **Optional NLP Dependencies**: `transformers` and `torch` (for local GPU/CPU FinBERT inference), `sentence-transformers` (for neural embeddings).

### Installation

Clone the repository and set up a virtual environment:

#### PowerShell (Windows):
```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
pip install -r requirements.txt
$env:PYTHONPATH = "src"
```

#### Bash / macOS / Linux:
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
export PYTHONPATH="src"
```

---

## Running the Application

### 1. Launch the Streamlit Dashboard

Initialize the SQLite database and launch the interactive web dashboard:

```powershell
python -c "from equity_news_engine.database import initialize_database; initialize_database()"
streamlit run app.py
```

Open `http://localhost:8501` in your browser. The dashboard contains 8 comprehensive views:
* **Search**: Run the complete real-time intelligence pipeline for any company or ticker, or view past runs.
* **Overview**: Ticker coverage metrics, independent sources, weighted & rolling sentiment, and recent execution logs.
* **News Feed**: Filterable table of all discovered articles with relevance scores and provenance links.
* **Events**: Discovered financial events with event-type distribution, importance timeline, and underlying articles.
* **Sentiment**: Model breakdown, probability distributions ($P_{pos}, P_{neu}, P_{neg}$), and sentiment dispersion.
* **Timeline**: Interactive chronology of announcements, filings, and news volume over time.
* **Sources**: Breakdown of registered publishers, regulatory sources, and primary source ratios.
* **Export**: Filter and export articles CSV, events CSV, daily features CSV, and full intelligence reports in JSON.

---

### International equity coverage

The collection command accepts a company name, ticker, or supported alias. NSE entries resolve locally; other listed equities can be looked up through Yahoo Finance's public symbol search and must match an exact ticker or company name. International news uses localized Google News search and the exchange-qualified Yahoo Finance feed; NSE, BSE and SEBI announcement collectors run only for Indian profiles. Public search and RSS coverage depends on upstream availability and is not guaranteed for every listing. Add `--start-date` / `--end-date` to scope collection, `--semantic-similarity-threshold` to tune near-duplicate clustering, and `--fetch-article-text` to attempt bounded page extraction. Collector errors and unsupported sources are retained in the collection run. To verify the pipeline without network access, run `python run_demo.py` (synthetic demo input; it does not touch the application database).

### 2. End-to-End Analysis CLI (Group 4 Orchestration)

To run the full integrated pipeline for an equity from the command line:

```powershell
python run_intelligence.py Reliance
```

Optional CLI arguments:
* `--start-date YYYY-MM-DD`: Earliest publication date to collect.
* `--end-date YYYY-MM-DD`: Latest publication date to collect.
* `--fetch-article-text`: Attempt live web extraction for article bodies (up to 20 URLs by default).
* `--semantic-similarity-threshold 0.65`: Tune near-duplicate clustering threshold.
* `--database data/equity_news.db`: Custom SQLite database path.

---

### 3. Module CLI Runners & Demos

Each subsystem can be tested independently:

#### Group 1 CLI (Resolution & News Discovery):
```powershell
python test_run.py "Tata Motors"
python test_run.py "INFY"
```

#### Group 2 CLI (Cleaning, Relevance & Deduplication):
```powershell
# Using the production pipeline
python group2_pipeline.py mock_raw_articles.json final_articles.json

# Or using the root compatibility runner
python pipeline.py mock_raw_articles.json final_articles.json
```

#### Group 3 Demo (Offline Event Intelligence & Quant Feature Generation):
```powershell
python run_demo.py
# Ingests mock clean articles, runs sentiment + event clustering + quant features,
# and outputs events.json and daily_features.csv to data/output/
```

---

## FinBERT & Sentiment Configuration

Group 3 uses **ProsusAI/FinBERT** by default for financial sentiment classification.

* **FinBERT-only default**: The pipeline requires FinBERT and fails the sentiment stage if the model cannot initialize or inference fails. It does not silently substitute a lexicon score.
* **Model Provenance**: The active model (`ProsusAI/finbert`) and any model error are recorded in collection run metadata.
* **Configuration via Environment Variables**:
  * `SENTIMENT_MODEL`: Set to `finbert` (default) or `lexicon` to force the lexicon model.
  * `SENTIMENT_FALLBACK_ENABLED`: Defaults to `false`. Keep it false to require FinBERT and fail clearly if unavailable.
  * `SENTIMENT_DEVICE`: Set to `cpu`, `cuda`, or an integer GPU ID (`-1` for CPU, `0` for CUDA:0).
  * `SENTIMENT_LOCAL_FILES_ONLY`: Set to `true` to disable network downloads and use local cache only.
* **Strict Verification**:
  ```powershell
  python scripts/verify_finbert.py
  ```

---

## Shared Interfaces & Data Contracts

All subsystems communicate via strict, verified data contracts:

### Group 1 $\rightarrow$ Group 2 (Raw Article Record)
```json
{
  "ticker": "RELIANCE",
  "company_name": "Reliance Industries Limited",
  "title": "Reliance Q2 Net Profit Jumps 16%...",
  "description": "Reliance Industries reported consolidated net profit...",
  "url": "https://www.bseindia.com/corporates/ann.aspx?id=101",
  "source": "BSE",
  "source_type": "EXCHANGE_FILING",
  "primary_source": true,
  "published_at": "2025-10-20T10:00:00Z",
  "first_seen_at": "2025-10-20T10:02:00Z",
  "retrieved_at": "2025-10-20T10:03:00Z",
  "collector": "bse_collector"
}
```

### Group 2 $\rightarrow$ Group 3 (Clean Article Record)
```json
{
  "article_id": "ARTICLE_783DC42DA7B7",
  "ticker": "RELIANCE",
  "company_name": "Reliance Industries Limited",
  "title": "Reliance Q2 Net Profit Jumps 16%...",
  "clean_text": "Reliance Q2 Net Profit Jumps 16%...",
  "source": "BSE",
  "source_type": "EXCHANGE_FILING",
  "published_at": "2025-10-20T10:00:00Z",
  "first_seen_at": "2025-10-20T10:02:00Z",
  "relevance_score": 1.0,
  "duplicate_cluster_id": "CLUSTER_A3FA201B8623",
  "primary_source": true,
  "independent_source": true
}
```

### Group 3 $\rightarrow$ Group 4 (Event Record)
```json
{
  "event_id": "EVT-35205d9afd",
  "ticker": "RELIANCE",
  "event_type": "EARNINGS",
  "event_timestamp": "2025-10-20T10:00:00Z",
  "headline": "Reliance Industries Q2 Profit Surges Driven by Retail and Jio Growth",
  "sentiment_score": 0.79,
  "sentiment_model_name": "ProsusAI/finbert",
  "positive_probability": 0.84,
  "neutral_probability": 0.11,
  "negative_probability": 0.05,
  "importance_score": 0.80,
  "article_count": 3,
  "independent_source_count": 3,
  "primary_source_present": true
}
```

### Group 3 $\rightarrow$ Group 4 (Daily Quant Features)
A 27-column financial feature dataset including:
* `date`, `ticker`
* `news_count`, `relevant_article_count`, `unique_event_count`
* `positive_event_count`, `negative_event_count`, `neutral_event_count`
* `weighted_sentiment`, `mean_sentiment`
* `sentiment_1d`, `sentiment_3d`, `sentiment_7d`, `sentiment_30d`, `sentiment_momentum`
* `news_volume`, `news_volume_zscore`, `news_volume_shock`
* `positive_shock`, `negative_shock`
* `mean_importance`, `max_importance`
* `source_agreement`, `sentiment_dispersion`
* `primary_source_event_count`

---

## Testing & Verification

The repository contains isolated unit and integration test suites covering all four groups.

```powershell
# Set Python path (PowerShell)
$env:PYTHONPATH = "src"

# Run Group 1 verification suite (Equity Resolver, Queries, RSS/Exchange Collectors)
python run_tests.py

# Run Group 2 test suite (Extraction, Cleaning, Relevance, Exact/Semantic Deduplication)
python -m pytest tests/test_extraction.py tests/test_cleaning.py tests/test_relevance.py tests/test_deduplication.py

# Run Group 3 test suite (FinBERT Sentiment, Clustering, Classification, Quant Features)
python -m pytest tests/test_sentiment.py tests/test_event_*.py tests/test_features.py

# Run repository-wide test suite
python -m pytest -q
```

---

## Database Architecture (SQLite)

The production database (`data/equity_news.db`) contains 8 relational tables:

1. `EQUITIES`: Canonical company metadata, ticker, exchange, ISIN, country, and aliases.
2. `SOURCES`: Registered news and regulatory sources with source type and primary-source status.
3. `ARTICLES`: Raw and cleaned articles with extraction status, relevance scores, cluster IDs, and timestamps.
4. `EVENTS`: Financial events with event type, representative headline, sentiment score, importance, and source counts.
5. `ARTICLE_EVENT_MAP`: Many-to-many join table connecting individual articles to clustered events.
6. `SENTIMENT_RESULTS`: Detailed sentiment scores and full probability vectors ($P_{pos}, P_{neu}, P_{neg}$) with model versioning.
7. `DAILY_FEATURES`: Point-in-time daily quantitative sentiment and volume metrics per ticker.
8. `COLLECTION_RUNS`: End-to-end execution audit logs capturing configuration, collector statuses, and error details.

---

## Shared Engineering Rules

1. **Zero Paid Dependencies**: The core system runs entirely on free public RSS feeds, public regulatory endpoints, and open-source models.
2. **Modular Architecture**: Subsystems communicate strictly through defined schemas; internal logic is decoupled.
3. **Configurable Thresholds**: Relevance thresholds, similarity cutoffs, time-decay rates, and shock limits are parameter-driven.
4. **Preserve Raw Data**: Original collected records and raw HTML are preserved separately and never overwritten by cleaned data.
5. **Preserve Timestamps**: Never invent missing timestamps; invalid or missing publication dates remain `None`.
6. **Graceful Degradation**: Extraction blocks or individual source failures are logged as partial failures and never crash the run.
7. **No Trading Logic**: The platform produces equity news intelligence and quantitative feature sets; trading strategies remain strictly external.
