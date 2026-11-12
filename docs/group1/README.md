# Group 1 News Collection Module

This module resolves equity queries, generates collection queries, and returns candidate news and announcement records. It is part of the integrated Equity News Intelligence application; the root [README](../../README.md) describes repository setup and the combined test suite.

## Setup and verification

From the repository root, install dependencies with `pip install -r requirements.txt`. Run Group 1's standalone checks with `python run_tests.py` and the complete Groups 1–4 suite with `python -m pytest -q`.

## Collection contract

Each raw record includes `ticker`, `company_name`, `title`, `description`, `url`, `source`, `source_type`, `primary_source`, `published_at`, `first_seen_at`, and `retrieved_at`. `collector` and `raw_url` retain collector identity and the original source URL when one is resolved. Missing publication dates remain null. Naive Indian exchange timestamps are interpreted as Asia/Kolkata and normalized to UTC.

Collector results distinguish `success`, `no_results`, `failed`, `partially_successful`, and `unsupported`; errors, warnings, and unsupported reasons are returned with the records. The pipeline passes generated queries to enabled collectors and returns run metadata and per-collector results.

## Source provenance and limits

- Direct NSE/BSE announcements and SEBI releases are marked primary only when collected from those official endpoints.
- Google News results used by the NSE or SEBI fallback path remain secondary `NEWS_RSS` records. Publisher name and resolved publisher URL are retained, with the original Google URL in `raw_url`.
- BSE collection requires a verified six-digit `bse_scrip_code` on the equity profile. No NSE ticker is sent as a BSE code. The current equity seed does not establish that mapping, so unsupported is returned until a verified mapping is configured.
- Company IR collection is configurable through `collectors.company_ir.feeds_by_ticker` in `config/default_config.yaml`. No feed is guessed. A feed is marked primary only when its configuration explicitly sets `primary_source: true`; unconfigured collection reports unsupported.
- Generic and Google News RSS records are secondary. No collector invents publication timestamps.

## Integration entry point

`pipeline.collect_equity_news(query, start_date=None, end_date=None, config_path="config/default_config.yaml", run_id=None)` returns the resolved equity, raw candidate records, structured collection status, collector results, errors, generated query categories, and collection run timestamps. Date-only bounds use the Asia/Kolkata calendar day; records outside the requested window and undated records are excluded when a window is requested.

Network collectors use public endpoints and can return no results or partial failures when sources are unavailable. Tests use synthetic fixtures and `.test` URLs in isolated temporary locations; they are not real financial records.
