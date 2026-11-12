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
tests/                          # Unit and integration test suite
```

---

## Quickstart & Testing

### 1. Installation

Python 3.10+ is recommended. Install the dependencies, including PyTorch and Transformers for primary FinBERT inference:

```bash
pip install -r requirements.txt
```

FinBERT is the default model (`ProsusAI/finbert`). On first use, Transformers downloads the tokenizer and model weights into the Hugging Face cache; the weights are not stored in this repository. A working network connection is needed unless the model is already cached. The lexicon fallback remains enabled by default and is selected before inference if FinBERT cannot initialize. Inference failures also trigger a warning and a complete rescore with the lexicon model when fallback is enabled. The selected model and fallback reason are available as `result.sentiment_model_name` and `result.sentiment_fallback_reason`.

#### Model selection and fallback

Environment configuration is read when the pipeline selects its default model:

| Setting | Default | Values |
| --- | --- | --- |
| `SENTIMENT_MODEL` | `finbert` | `finbert` or `lexicon` |
| `SENTIMENT_FALLBACK_ENABLED` | `true` | `true` or `false` |
| `SENTIMENT_LOCAL_FILES_ONLY` | `false` | `true` or `false`; prevent model download |
| `SENTIMENT_DEVICE` | automatic | `-1` for CPU, `0` for first CUDA GPU |

For PowerShell, require FinBERT with no fallback and run on CPU:

```powershell
$env:SENTIMENT_MODEL = "finbert"
$env:SENTIMENT_FALLBACK_ENABLED = "false"
$env:SENTIMENT_DEVICE = "-1"
python run_demo.py
```

Choose the lexicon model explicitly:

```powershell
$env:SENTIMENT_MODEL = "lexicon"
python run_demo.py
```

The same settings can be passed through `SentimentConfig` to `run_group3_pipeline`, for example `sentiment_config=SentimentConfig(model="lexicon")`.

#### FinBERT troubleshooting

- Install model dependencies with `pip install transformers torch` (or rerun `pip install -r requirements.txt`).
- If the first-run download is blocked, allow access to the Hugging Face model repository, then rerun. For an offline run, download/cache the model first and set `SENTIMENT_LOCAL_FILES_ONLY=true`.
- Use `SENTIMENT_FALLBACK_ENABLED=false` to surface download, cache, or inference errors instead of falling back.
- Set `SENTIMENT_DEVICE=-1` to force CPU execution. Leave it unset for automatic CUDA selection when available.
- Do not copy model weight files into the repository; cache paths are ignored by Git.

### 2. Run Test Suite

Run the unit and integration test suite:

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

## Verifying Real FinBERT Inference on Windows

The verification script performs real inference through the project's `FinBERTSentimentModel`. It bypasses model resolution and lexicon fallback, and exits nonzero if the real model cannot initialize or any probability/provenance check fails.

Install the project dependencies, including `transformers` and `torch`:

```powershell
python -m pip install -r requirements.txt
```

Set strict verification options in PowerShell and run the script from the repository root:

```powershell
$env:SENTIMENT_MODEL="finbert"
$env:SENTIMENT_FALLBACK_ENABLED="false"
$env:SENTIMENT_LOCAL_FILES_ONLY="false"
$env:SENTIMENT_DEVICE="cpu"
python scripts/verify_finbert.py
```

On first use, Transformers downloads the `ProsusAI/finbert` tokenizer and pretrained weights from Hugging Face into its local cache. The download may take time; later runs reuse the cache. The verification prints each sample text, predicted label, positive/negative/neutral probabilities, sentiment score, and model provenance. It prints a success message only after all real inference and probability checks pass. Provenance must be `ProsusAI/finbert`.

After verification succeeds, run the full pipeline with the same strict settings:

```powershell
python run_demo.py
```

The demo prints its selected model, and every event record contains `sentiment_model_name` for provenance. It generates the unchanged Group 4 event and daily feature schemas plus the existing additive event audit fields.

To run lexicon sentiment explicitly instead, select it directly:

```powershell
$env:SENTIMENT_MODEL="lexicon"
$env:SENTIMENT_FALLBACK_ENABLED="true"
python run_demo.py
```

This reports provenance as `lexicon`. A lexicon model activated after a FinBERT initialization or inference error reports `lexicon-fallback` and includes the failure reason. Fallback can be disabled to make either failure stop the run.

Troubleshooting:

- For missing packages, rerun `python -m pip install -r requirements.txt` in the same Python environment used to run the script.
- If model download fails, check access to Hugging Face and rerun with `SENTIMENT_LOCAL_FILES_ONLY="false"`. Set it to `true` only after the model is present in the local cache.
- For CPU-only execution, use `SENTIMENT_DEVICE="cpu"`; the pipeline maps this to Transformers' CPU device. CUDA is selected automatically if no device is specified and CUDA is available.
- Keep downloaded weights in the Hugging Face cache. Cache directories and pretrained weight files are excluded from Git; do not commit them.

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
| `positive_probability` | `float` | Selected sentiment model's aggregate positive probability $\in [0, 1]$ |
| `neutral_probability` | `float` | Selected sentiment model's aggregate neutral probability $\in [0, 1]$ |
| `negative_probability` | `float` | Selected sentiment model's aggregate negative probability $\in [0, 1]$ |
| `importance_score` | `float` | Multi-factor importance score $\in [0, 1]$ |
| `article_count` | `int` | Number of articles describing this event |
| `independent_source_count` | `int` | Count supported by explicit independence/origin metadata |
| `publisher_count` | `int` | Distinct publisher names; not treated as proof of independent origins |
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
| `news_volume_shock` | `int` | Configured news-volume shock when the z-score reaches `volume_z_threshold` |
| `positive_shock` | `int` | `1` if daily sentiment $\ge +0.5$, else `0` |
| `negative_shock` | `int` | `1` if daily sentiment $\le -0.5$, else `0` |
| `mean_importance` | `float` | Average daily event importance |
| `max_importance` | `float` | Maximum daily event importance |
| `source_agreement` | `float` | Agreement metric among publisher groups $\in [0, 1]$; publisher grouping does not prove source independence |
| `sentiment_dispersion` | `float` | Population standard deviation of event sentiment |
| `primary_source_event_count`| `int` | Events confirmed by primary filings/announcements |

---

## Core Methodologies

### 1. Financial Sentiment (FinBERT)
Articles are scored using `ProsusAI/finbert` when its tokenizer and weights initialize successfully. If configured, initialization failure selects `LexiconSentimentModel` before inference and records the model name and fallback reason in `Group3PipelineResult`. Inference failures do not trigger a model switch. Probabilities are strictly preserved:
$$\text{sentiment\_score} = P(\text{positive}) - P(\text{negative}) \quad \in [-1, 1]$$
At the **event level**, repeated publisher coverage does not dominate: articles from the same publisher are averaged first, and primary sources receive a configured multiplier. Publisher grouping does not assert source independence. Probabilities are renormalized before computing the event score.

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
