# Equity News Intelligence Engine — Group 1
> **Subsystem**: Equity Resolution & Multi-Source News/Announcement Collection  
> **Pipeline Role**: `USER QUERY → CANONICAL EQUITY → RAW NEWS & FILINGS STREAM`

---

## Overview

Group 1 is the foundational ingestion layer of the Equity News Intelligence & Sentiment Engine. It takes free-form, noisy user inputs (e.g., `"relaince"`, `"SBI"`, `"Tata Motors"`), resolves them into canonical publicly listed equities across all **2,620+ active NSE companies**, generates targeted multi-category queries, and concurrently collects hundreds of candidate articles, exchange announcements, and regulatory releases from free public sources.

---

## Quickstart: Running on Any Device

### Prerequisites
* Python 3.9+ (Python 3.10–3.12 recommended)
* Git

---

### Method A: With Virtual Environment (Recommended)

#### 1. Clone the repository
```bash
git clone https://github.com/MeetBatheja/News_Collect.git
cd News_Collect
```

#### 2. Create and activate a virtual environment
* **macOS / Linux**:
  ```bash
  python3 -m venv .venv
  source .venv/bin/activate
  ```
* **Windows (Command Prompt / PowerShell)**:
  ```cmd
  python -m venv .venv
  .venv\Scripts\activate
  ```

#### 3. Install dependencies
```bash
pip install -r requirements.txt
```

#### 4. Run tests & smoke test
```bash
# Verify system (7/7 tests)
python run_tests.py

# Test any company query
python test_run.py "Zomato"
```

---

### Method B: Without Virtual Environment (Direct System Python)

If you prefer to run directly without creating a virtual environment:

#### 1. Clone the repository
```bash
git clone https://github.com/MeetBatheja/News_Collect.git
cd News_Collect
```

#### 2. Install dependencies directly
* **macOS / Linux**:
  ```bash
  pip3 install -r requirements.txt
  ```
  *(If your system uses managed environments, run: `pip3 install --user -r requirements.txt`)*

* **Windows**:
  ```cmd
  pip install -r requirements.txt
  ```

#### 3. Run tests & collection
* **macOS / Linux**:
  ```bash
  python3 run_tests.py
  python3 test_run.py "Tata Motors"
  ```
* **Windows**:
  ```cmd
  python run_tests.py
  python test_run.py "Tata Motors"
  ```

---

## Integration Guide for Downstream Groups

### How Group 4 (Integration / Dashboard) Calls Group 1
Import the master pipeline entrypoint from `pipeline.py`:

```python
from pipeline import collect_equity_news

# One-line invocation
result = collect_equity_news(
    query="Reliance",           # Any ticker, alias, or typo
    start_date="2026-10-01",    # Optional ISO date string
    end_date="2026-10-31"       # Optional ISO date string
)

print(result["status"])           # "SUCCESS" | "NO_ARTICLES" | "FAILED"
print(result["equity_profile"])   # Canonical profile dict
print(result["total_articles"])   # e.g., 384
print(result["collector_stats"])  # {"google_news_rss": 220, "nse_collector": 100, ...}
```

---

### How Group 2 (Extraction & Cleaning) Consumes Group 1 Data

Group 1 provides two ways to consume data:

#### 1. Live Python Stream:
`result["raw_articles"]` contains a list of standardized dictionaries matching the agreed `RawArticleRecord` contract:

```json
{
  "company_name": "Reliance Industries Limited",
  "ticker": "RELIANCE",
  "title": "Reliance Q2 profit beats analyst estimates on strong retail growth",
  "description": "Billionaire Mukesh Ambani's Reliance Industries Ltd reported...",
  "url": "https://www.livemint.com/market/reliance-q2-earnings-2026",
  "source": "Livemint",
  "source_type": "NEWS_RSS",
  "primary_source": false,
  "published_at": "2026-10-27T14:15:00Z",
  "first_seen_at": "2026-10-31T07:10:00Z",
  "retrieved_at": "2026-10-31T07:10:00Z",
  "collector": "GoogleNewsRSSCollector"
}
```

#### 2. Offline Mock Sample for Development:
Group 2 can develop and unit-test extractors immediately without live network requests by loading:
```text
data/raw/samples/mock_raw_articles.json
```

---

## 📋 Data Contract & Standards

### Allowed `source_type` Vocabulary
* `EXCHANGE_FILING`: Official announcements submitted to NSE or BSE.
* `REGULATORY`: Enforcement orders, warnings, or circulars from SEBI.
* `COMPANY_IR`: Press releases from official investor relations channels.
* `NEWS_RSS`: Articles discovered via Google News and media RSS feeds.
* `AGGREGATOR`: Multi-source aggregations (e.g., Business Standard, Moneycontrol).

### Strict Timestamp Integrity
* `published_at`: Standardized UTC ISO-8601 (`YYYY-MM-DDTHH:MM:SSZ`). If unavailable or unparseable, it is strictly `null` (`None`). **The system never invents publication dates.**
* `first_seen_at` & `retrieved_at`: Point-in-time capture timestamps recording discovery time.

---

## Repository Structure

```text
News_Collect/
├── config/
│   ├── default_config.yaml         # Timeouts, rate limits, and collector toggles
│   └── query_templates.json        # 11+ financial category search templates
├── data/
│   ├── seed/
│   │   ├── nse_listed_companies.csv   # Master list of all 2,620 active NSE equities
│   │   └── equity_aliases_seed.json   # Known abbreviations (RIL, SBI, TaMo, L&T)
│   ├── cache/                      # Local SQLite cache for rapid re-resolution
│   └── raw/                        # Immutable raw JSON/XML archive ({TICKER}/)
│       └── samples/
│           └── mock_raw_articles.json # Contract mock dataset for Group 2
├── equity/
│   ├── profile.py                  # Pydantic EquityProfile data model
│   ├── resolver.py                 # Typo-tolerant Damerau-Levenshtein fuzzy resolver
│   └── query_generator.py          # Category query generator
├── collectors/
│   ├── base_collector.py           # BaseCollector ABC + RawArticleRecord schema
│   ├── google_news_rss.py          # High-volume Google News search collector
│   ├── generic_rss_collector.py    # Financial RSS & Yahoo Finance ticker feed
│   ├── nse_collector.py            # Primary NSE corporate announcements
│   ├── bse_collector.py            # Primary BSE corporate announcements
│   └── sebi_collector.py           # Primary SEBI regulatory orders & releases
├── utils/
│   ├── http_client.py              # Requests session with retries & browser headers
│   ├── timestamp_parser.py         # UTC ISO-8601 timestamp normalizer
│   ├── url_resolver.py             # Redirect resolver for Google News links
│   └── logger.py                   # Formatted logger with run_id support
├── pipeline.py                     # Master orchestrator entrypoint
├── test_run.py                     # Interactive CLI tool to test any equity query
├── run_tests.py                    # Complete verification test suite
└── requirements.txt                # Production dependencies
```

---

## Testing & Verification

Run the test suite:
```bash
python run_tests.py
```

Expected output:
```text
==================================================
        EQUITY NEWS INTELLIGENCE - GROUP 1        
              SYSTEM VERIFICATION                 
==================================================
✓ test_equity_profile passed
✓ test_full_universe_loaded passed (2620 NSE equities active)
✓ test_typo_and_transposition_tolerance passed ('relaince', 'Relancie', 'Tatamotrs', 'Infsys')
✓ test_acronym_and_informal_resolution passed ('SBI', 'SBI Bank', 'L&T', 'HDFC', 'Wipro', 'Zomato')
✓ test_timestamp_parser passed (strictly normalizes to UTC ISO-8601, zero date invention)
✓ test_query_generator passed (37 unique queries generated across categories)
✓ test_raw_article_record_schema passed (conforms to Group 1 -> Group 2 contract)

--------------------------------------------------
Result: 7/7 tests passed.
ALL TESTS PASSED WITH 100% SUCCESS!
```

---

## License
This repository is part of the Equity News Intelligence & Sentiment Engine academic/quant research initiative.
