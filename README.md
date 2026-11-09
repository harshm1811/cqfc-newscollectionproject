# Group 3: Event Intelligence, Sentiment & Quant Features Engine

Part of the **Equity News Intelligence & Sentiment Engine** project.

Group 3 takes cleaned, deduplicated equity news from Group 2 and converts it into structured financial events, sentiment intelligence, and point-in-time quantitative feature datasets for downstream consumption by Group 4 (Database, Reporting, and Dashboard).

```text
                  GROUP 1: Equity Resolution + News Collection
                                      │
                                      ▼
             GROUP 2: Data Cleaning + Relevance + Deduplication
                                      │  Clean Article Records
                                      ▼
               ┌──────────────────────────────────────────────┐
               │                   GROUP 3                    │
               │        EVENT INTELLIGENCE & SENTIMENT        │
               │                                              │
               │   1. Financial Sentiment (FinBERT / Lexicon) │
               │   2. Event Clustering (TF-IDF / Embeddings)  │
               │   3. Event Classification (20 Categories)    │
               │   4. Multi-Factor Importance & Decay         │
               │   5. Quantitative Feature Engine             │
               └──────────────────────┬───────────────────────┘
                                      │
                       ┌──────────────┴──────────────┐
                       ▼                             ▼
                 EVENT DATASET             DAILY FEATURE DATASET
                       │                             │
                       └──────────────┬──────────────┘
                                      │
                                      ▼
             GROUP 4: Database + Reporting + Dashboard + Integration
```

---

## Repository Layout

```text
events/
  event_model.py                # Data contracts: Article, Event, SentimentResult, mappings
  event_clusterer.py            # Event clustering engine with time-window & duplicate constraints
models/
  sentiment.py                  # FinBERT (ProsusAI/finbert) & Lexicon fallback sentiment models
  event_classifier.py           # Classifier covering 20 financial event categories
  importance.py                 # Multi-factor event importance scoring engine
  source_quality.py             # Source categorization, weights, and corroboration scoring
  _records.py                   # Mapping/object conversion helpers
aggregation/
  event_scoring.py              # Orchestrator for event importance, source quality, and time decay
  time_decay.py                 # Exponential time-decay functions (half-life formulation)
  sentiment_index.py            # Event weighted sentiment aggregation
  rolling.py                    # Rolling calendar sentiment windows (1D, 3D, 7D, 30D) and momentum
  feature_engine.py             # Point-in-time ticker/day quantitative feature pipeline
  adapters/input_adapter.py     # Adapter normalizing upstream inputs for feature engineering
config/
  importance.yaml               # Importance factor weights and event-type scores
  source_quality.yaml           # Source categories, weights, and confirmation multipliers
  decay.yaml                    # Half-life configuration and timestamp rules
data/
  mock/
    mock_group2_articles.json   # Multi-day mock dataset strictly conforming to Group 2 interface
pipeline.py                     # Central Group 3 pipeline orchestrator (run_group3_pipeline)
run_demo.py                     # Interactive test runner and dataset exporter
tests/                          # Pytest suite (68 unit and integration tests)
```

---

## Quickstart & Testing

### 1. Installation

Python 3.10+ is recommended. Install the dependencies:

```bash
pip install -r requirements.txt
```

*(Note: PyTorch and Transformers are optional; if installed, the engine will automatically use `ProsusAI/finbert`. Otherwise, it seamlessly falls back to the local `LexiconSentimentModel` without error).*

### 2. Run Test Suite

Run all 68 unit and integration tests:

```bash
pytest -v
```

### 3. Run the Interactive Demo

Execute the end-to-end pipeline against the mock Group 2 dataset:

```bash
python run_demo.py
```

To run with your own custom JSON file:

```bash
python run_demo.py --input path/to/your_articles.json
```

The demo displays:
- Discovered financial events with sentiment and importance scores.
- Daily quantitative features (rolling sentiment, momentum, volume z-scores, shock flags).
- Exports datasets to `data/output/events.json` and `data/output/daily_features.csv` ready for Group 4.

---

## Shared Interfaces

### Upstream Input (Group 2 $\rightarrow$ Group 3)

Group 3 consumes **Clean Article Records** from Group 2. Each record can be a dictionary or object exposing:

| Field | Type | Description |
| :--- | :--- | :--- |
| `article_id` | `str` | Unique article identifier assigned by Group 2 |
| `ticker` | `str` | Canonical equity ticker (e.g., `"RELIANCE"`, `"TCS"`) |
| `title` | `str` | Article headline |
| `clean_text` | `str` | Cleaned boilerplate-free article text |
| `source` | `str` | Publisher / source name (e.g., `"BSE"`, `"Mint"`, `"Reuters"`) |
| `source_type` | `str` | Source type (`"EXCHANGE_FILING"`, `"NEWS_RSS"`, etc.) |
| `published_at` | `str` / `datetime` | UTC publication timestamp |
| `first_seen_at` | `str` / `datetime` | UTC discovery timestamp |
| `relevance_score` | `float` | Equity relevance score $\in [0, 1]$ |
| `duplicate_cluster_id`| `str` | Semantic deduplication cluster assigned by Group 2 |
| `primary_source` | `bool` | `True` for exchange filings, regulatory releases, IR |
| `independent_source`| `bool` | `True` for non-syndicated independent reporting |

### Downstream Output (Group 3 $\rightarrow$ Group 4)

Group 3 produces two standardized outputs for Group 4:

#### 1. Event Dataset (`EVENT DATASET`)
Accessed via `result.event_records` or `result.events_df`:

| Field | Type | Description |
| :--- | :--- | :--- |
| `event_id` | `str` | Unique deterministic event identifier (`EVT-...`) |
| `ticker` | `str` | Canonical equity ticker |
| `event_type` | `str` | One of the 20 financial event categories |
| `event_timestamp` | `str` (ISO-8601) | Earliest verified article timestamp in event |
| `headline` | `str` | Representative event headline (cluster centroid) |
| `sentiment_score` | `float` | Event sentiment score $\in [-1, 1]$ |
| `positive_probability` | `float` | FinBERT aggregate positive probability $\in [0, 1]$ |
| `neutral_probability` | `float` | FinBERT aggregate neutral probability $\in [0, 1]$ |
| `negative_probability` | `float` | FinBERT aggregate negative probability $\in [0, 1]$ |
| `importance_score` | `float` | Multi-factor importance score $\in [0, 1]$ |
| `article_count` | `int` | Number of articles describing this event |
| `independent_source_count` | `int` | Count of independent reporting sources |
| `primary_source_present` | `bool` | `True` if confirmed by a primary source |

#### 2. Daily Equity Feature Dataset (`DAILY FEATURE DATASET`)
Accessed via `result.daily_features` (`DataFrame`):

| Column | Type | Description |
| :--- | :--- | :--- |
| `date` | `date` | Trading / calendar date (normalized UTC) |
| `ticker` | `str` | Equity ticker |
| `news_count` | `int` | Total article count discovered for that date |
| `relevant_article_count` | `int` | Articles exceeding relevance threshold |
| `unique_event_count` | `int` | Distinct financial events on that date |
| `positive_event_count` | `int` | Events with positive sentiment ($\text{score} > 0$) |
| `negative_event_count` | `int` | Events with negative sentiment ($\text{score} < 0$) |
| `neutral_event_count` | `int` | Events with neutral sentiment ($\text{score} = 0$) |
| `mean_sentiment` | `float` | Unweighted average event sentiment $\in [-1, 1]$ |
| `weighted_sentiment` | `float` | Normalized weighted sentiment by relevance, importance, source quality, decay |
| `sentiment_1d` | `float` | 1-day trailing sentiment |
| `sentiment_3d` | `float` | 3-day trailing sentiment |
| `sentiment_7d` | `float` | 7-day trailing sentiment |
| `sentiment_30d` | `float` | 30-day trailing sentiment |
| `sentiment_momentum` | `float` | Sentiment momentum ($\text{Sentiment}_{1\text{D}} - \text{Sentiment}_{7\text{D}}$) |
| `news_volume` | `int` | Unique event volume |
| `news_volume_zscore` | `float` | Rolling z-score of daily event volume |
| `positive_shock` | `int` | `1` if daily sentiment $\ge +0.5$, else `0` |
| `negative_shock` | `int` | `1` if daily sentiment $\le -0.5$, else `0` |
| `mean_importance` | `float` | Average daily event importance |
| `max_importance` | `float` | Maximum daily event importance |
| `source_agreement` | `float` | Agreement metric among independent sources $\in [0, 1]$ |
| `sentiment_dispersion` | `float` | Population standard deviation of event sentiment |
| `primary_source_event_count`| `int` | Events confirmed by primary filings/announcements |

---

## Core Methodologies

### 1. Financial Sentiment (FinBERT)
Articles are scored using `ProsusAI/finbert` (or `LexiconSentimentModel` when running offline). Probabilities are strictly preserved:
$$\text{sentiment\_score} = P(\text{positive}) - P(\text{negative}) \quad \in [-1, 1]$$
At the **event level**, syndicated copies do not dominate: articles from the same independent source are averaged first, and primary sources receive a configured multiplier. Probabilities are renormalized before computing the event score.

### 2. Event Clustering
Combines TF-IDF / vector embeddings with temporal constraints (`time_window_hours`, `max_cluster_age_hours`) and Group 2's `duplicate_cluster_id`. Articles for different tickers are never merged. The representative headline is chosen as the article closest to the cluster centroid.

### 3. Event Classification
Rule-based regex engine tuned for Indian and global financial markets covering all **20 standard categories**:
`EARNINGS`, `GUIDANCE`, `MERGER_ACQUISITION`, `DIVIDEND`, `BUYBACK`, `CAPITAL_RAISE`, `DEBT_FINANCING`, `MANAGEMENT_CHANGE`, `PRODUCT_SERVICE`, `EXPANSION`, `CAPEX`, `MAJOR_CONTRACT`, `REGULATION`, `LITIGATION`, `INVESTIGATION`, `FRAUD`, `ANALYST_ACTION`, `SUBSIDIARY_EVENT`, `CORPORATE_ACTION`, `OTHER`.

### 4. Event Importance & Time Decay
- **Importance**: Combines 8 non-negative weighted factors defined in `config/importance.yaml`: event type baseline, financial magnitude, independent sources, primary confirmation, specificity, novelty, quantitative data, and breaking status.
- **Time Decay**:
  $$\text{time\_weight} = \exp(-\lambda \times \text{age}), \quad \lambda = \frac{\ln(2)}{\text{half\_life\_hours}}$$
  Configured in `config/decay.yaml` (default half-life: 72 hours).

### 5. Event Contribution Formula
An event's contribution to daily equity sentiment is defined as:
$$\text{Contribution} = \text{Sentiment} \times \text{Relevance} \times \text{Importance} \times \text{SourceQuality} \times \text{TimeWeight}$$
$$\text{WeightedSentiment} = \frac{\sum \text{Contribution}}{\sum (\text{Relevance} \times \text{Importance} \times \text{SourceQuality} \times \text{TimeWeight})}$$

---

## Python API Usage

To use Group 3 inside an integration script or pipeline:

```python
from pipeline import run_group3_pipeline

# 1. Provide articles from Group 2 (list of dicts or Article objects)
clean_articles = [...]

# 2. Run pipeline
result = run_group3_pipeline(
    clean_articles,
    to_snake_case=True,  # Formats columns for Group 4 SQLite table
)

# 3. Access deliverables
events_list = result.events              # List[Event] dataclasses
events_records = result.event_records    # List[dict] for Group 4 EVENT DATASET
events_df = result.events_df            # pd.DataFrame
daily_features_df = result.daily_features# pd.DataFrame for Group 4 DAILY FEATURES
```
