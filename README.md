# Equity News Intelligence Engine - Group 1
## Equity Resolution & News Collection

### Overview
Group 1 owns the first stage of the multi-group intelligence pipeline:
```
USER QUERY → RAW NEWS & ANNOUNCEMENT DATA
```
It resolves free-form company names into canonical equities, generates targeted financial search queries across 17+ categories, and gathers raw article metadata and exchange filings from public sources without paid APIs.

---

### Project Structure
```
news_collection_group1/
├── config/
│   ├── default_config.yaml         # Operational settings, timeouts, and rate limits
│   └── query_templates.json        # 17+ financial category search query templates
├── data/
│   ├── seed/
│   │   ├── nse_listed_companies.csv   # Master listing database for NSE equities
│   │   └── equity_aliases_seed.json   # Known aliases & major subsidiaries
│   ├── cache/                      # Local SQLite cache for rapid resolution
│   └── raw/                        # IMMUTABLE raw data store (organized by ticker)
│       └── samples/
│           └── mock_raw_articles.json # Contract mock records for Group 2
├── equity/
│   ├── profile.py                  # Pydantic EquityProfile data model
│   ├── resolver.py                 # Fuzzy matching & ticker resolution engine
│   └── query_generator.py          # Category query generator
├── collectors/
│   ├── base_collector.py           # Abstract Base Class + RawArticleRecord schema
│   ├── google_news_rss.py          # Google News RSS collector
│   ├── generic_rss_collector.py    # Public Indian media feeds (Mint, ET, BS)
│   ├── nse_collector.py            # NSE Corporate Announcements (Primary source)
│   ├── bse_collector.py            # BSE Announcements (Primary source)
│   ├── sebi_collector.py           # SEBI Orders & Releases (Regulatory source)
│   └── company_ir_collector.py     # Company Investor Relations / PR
├── utils/
│   ├── http_client.py              # Hardened requests session with retries & headers
│   ├── url_resolver.py             # Resolves Google News redirects to real publisher URLs
│   ├── timestamp_parser.py         # Standardizes timestamps to ISO-8601 UTC
│   └── logger.py                   # Standardized logger with run_id support
├── tests/                          # Complete offline test suite
├── pipeline.py                     # Main orchestrator entrypoint
└── requirements.txt
```

---

### Team Split (3 Members)

| Member | Focus | Key Files |
| :--- | :--- | :--- |
| **Person A** | **Foundation & Equity Core** | `equity/profile.py`, `equity/resolver.py`, `equity/query_generator.py`, `collectors/base_collector.py`, `tests/test_resolver.py`, `tests/test_query_generator.py` |
| **Person B** | **News Discovery (RSS)** | `collectors/google_news_rss.py`, `collectors/generic_rss_collector.py`, `utils/url_resolver.py`, `utils/timestamp_parser.py` |
| **Person C** | **Primary Sources (Exchanges & Regulators)** | `collectors/nse_collector.py`, `collectors/bse_collector.py`, `collectors/sebi_collector.py`, `collectors/company_ir_collector.py`, `tests/test_collectors.py` |

---

### Group 1 -> Group 2 Contract (Standard Collector Output)
Every collector outputs records conforming to this exact schema:
```json
{
  "company_name": "Reliance Industries Limited",
  "ticker": "RELIANCE",
  "title": "Reliance Industries Q2 Profit Rises 12%",
  "description": "Reliance reported consolidated net profit beat expectations...",
  "url": "https://www.livemint.com/...",
  "source": "Livemint",
  "source_type": "NEWS_RSS",
  "primary_source": false,
  "published_at": "2026-10-27T14:15:00Z",
  "first_seen_at": "2026-10-28T09:00:00Z",
  "retrieved_at": "2026-10-28T09:00:00Z",
  "collector": "GoogleNewsRSSCollector"
}
```

* **Valid `source_type` vocabulary**: `EXCHANGE_FILING`, `REGULATORY`, `COMPANY_IR`, `NEWS_RSS`, `AGGREGATOR`
* **Timestamp Rule**: Always ISO-8601 UTC string (`YYYY-MM-DDTHH:MM:SSZ`) or `null` if missing. **Never invent timestamps.**
* **Raw preservation**: All original HTTP responses must be saved in `data/raw/{ticker}/`.

---

### Getting Started

1. Create and activate a virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

2. Run the test suite:
```bash
pytest -v
```

3. Run pipeline smoke test:
```bash
python pipeline.py
```
