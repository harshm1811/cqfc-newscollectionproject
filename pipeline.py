"""
pipeline.py - Master Group 1 Pipeline Orchestration Entrypoint

Responsibilities:
1. Accept user input string (e.g. 'Reliance' or 'TCS') and date range.
2. Resolve user input into canonical EquityProfile.
3. Generate targeted category queries.
4. Concurrently run all enabled collectors (RSS, Exchange, Regulatory).
5. Persist raw payloads to data/raw/{ticker}/.
6. Return standardized raw candidate article stream for Group 2 & Group 4.
"""

from typing import Dict, Any, List, Optional
from datetime import date, datetime, time, timedelta, timezone
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from uuid import uuid4
from zoneinfo import ZoneInfo
import yaml

from equity.resolver import EquityResolver
from equity.query_generator import QueryGenerator
from collectors.google_news_rss import GoogleNewsRSSCollector
from collectors.generic_rss_collector import GenericRSSCollector
from collectors.nse_collector import NSECollector
from collectors.bse_collector import BSECollector
from collectors.sebi_collector import SEBICollector
from collectors.company_ir_collector import CompanyIRCollector
from utils.logger import get_logger
from utils.timestamp_parser import get_current_utc_iso, parse_to_utc_iso


def _parse_window_bound(value: Optional[str], *, end_of_day: bool = False) -> Optional[datetime]:
    if value is None:
        return None
    if not isinstance(value, str) or not value.strip():
        raise ValueError("Date bounds must be non-empty ISO-8601 strings")
    clean = value.strip()
    if len(clean) == 10:
        try:
            parsed_date = date.fromisoformat(clean)
        except ValueError:
            parsed_date = None
        if parsed_date is not None:
            local_time = time(23, 59, 59) if end_of_day else time.min
            return datetime.combine(parsed_date, local_time, ZoneInfo("Asia/Kolkata")).astimezone(timezone.utc)
    normalized = parse_to_utc_iso(clean)
    if normalized is None:
        raise ValueError(f"Invalid ISO-8601 date bound: {value}")
    return datetime.fromisoformat(normalized.replace("Z", "+00:00"))


def collect_equity_news(
    query: str,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    config_path: str = "config/default_config.yaml",
    run_id: Optional[str] = None
) -> Dict[str, Any]:
    """
    Main Group 1 Entrypoint Function.
    
    Args:
        query: Company name or ticker (e.g. 'Reliance', 'TCS', 'TATAMOTORS')
        start_date: Optional start date string (e.g. '2026-10-01')
        end_date: Optional end date string (e.g. '2026-10-28')
        config_path: Path to configuration YAML
        run_id: Optional tracking ID from Group 4
        
    Returns:
        Dict containing:
        - "equity_profile": dict
        - "raw_articles": list of RawArticleRecord dicts
        - "status": "SUCCESS" | "NO_ARTICLES" | "FAILED"
        - "collector_stats": dict
    """
    run_id = run_id or str(uuid4())
    started_at = get_current_utc_iso()
    logger = get_logger("group1_pipeline", run_id=run_id)
    logger.info(f"Initiating Group 1 News Collection for query: '{query}'")

    # 1. Load configuration
    config = {}
    cfg_file = Path(config_path)
    if not cfg_file.is_absolute() and not cfg_file.exists():
        cfg_file = Path(__file__).resolve().parent / cfg_file
    try:
        with open(cfg_file, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f) or {}
        if not isinstance(config, dict):
            raise ValueError("Configuration root must be a mapping")
    except Exception as e:
        completed_at = get_current_utc_iso()
        error = {"stage": "configuration", "error": str(e)}
        return {"equity_profile": None, "raw_articles": [], "total_articles": 0,
                "status": "FAILED", "collection_status": "failed", "errors": [error],
                "collector_stats": {}, "collector_results": {},
                "collection_run": {"run_id": run_id, "started_at": started_at,
                                   "completed_at": completed_at, "status": "failed"}}

    # Parse date arguments if provided
    try:
        max_lookback = max(1, int(config.get("general", {}).get("max_lookback_days", 14)))
        now = datetime.now(timezone.utc).replace(microsecond=0)
        dt_start = _parse_window_bound(start_date)
        dt_end = _parse_window_bound(end_date, end_of_day=True)
        if dt_start is None and dt_end is None:
            dt_end, dt_start = now, now - timedelta(days=max_lookback)
        elif dt_start is None:
            dt_start = dt_end - timedelta(days=max_lookback)
        elif dt_end is None:
            dt_end = now
        if dt_start > dt_end:
            raise ValueError("start_date must be earlier than or equal to end_date")
    except Exception as e:
        completed_at = get_current_utc_iso()
        error = {"stage": "date_window", "error": str(e)}
        return {"equity_profile": None, "raw_articles": [], "total_articles": 0,
                "status": "FAILED", "collection_status": "failed", "errors": [error],
                "collector_stats": {}, "collector_results": {},
                "collection_run": {"run_id": run_id, "started_at": started_at,
                                   "completed_at": completed_at, "status": "failed"}}

    # 2. Resolve Equity
    try:
        resolver = EquityResolver()
        profile = resolver.resolve(query)
    except Exception as e:
        profile = None
        resolution_error = str(e)
    else:
        resolution_error = None
    if not profile:
        logger.error(f"Could not resolve equity for query: '{query}'")
        return {
            "equity_profile": None,
            "raw_articles": [],
            "status": "FAILED",
            "collection_status": "failed",
            "message": resolution_error or f"Could not resolve equity '{query}'",
            "errors": [{"stage": "equity_resolution", "error": resolution_error or f"Could not resolve equity '{query}'"}],
            "collector_stats": {}, "collector_results": {},
            "collection_run": {"run_id": run_id, "started_at": started_at,
                               "completed_at": get_current_utc_iso(), "status": "failed"}
        }

    logger.info(f"Resolved to: {profile.company_name} ({profile.ticker}) on {profile.exchange}")

    # 3. Generate Queries
    query_gen = QueryGenerator()
    flat_queries = query_gen.get_flat_query_list(profile)
    logger.info(f"Generated {len(flat_queries)} targeted search queries across categories")

    # 4. Initialize enabled collectors
    collectors_cfg = config.get("collectors", {})
    collectors = []

    if collectors_cfg.get("google_news_rss", {}).get("enabled", True):
        collectors.append(GoogleNewsRSSCollector(config=config))
    if collectors_cfg.get("generic_rss", {}).get("enabled", True):
        collectors.append(GenericRSSCollector(config=config))
    if collectors_cfg.get("nse_announcements", {}).get("enabled", True):
        collectors.append(NSECollector(config=config))
    if collectors_cfg.get("bse_announcements", {}).get("enabled", True):
        collectors.append(BSECollector(config=config))
    if collectors_cfg.get("sebi_releases", {}).get("enabled", True):
        collectors.append(SEBICollector(config=config))
    if collectors_cfg.get("company_ir", {}).get("enabled", False):
        collectors.append(CompanyIRCollector(config=config))

    # 5. Execute collectors in parallel
    all_records = []
    stats: Dict[str, int] = {}
    collector_results: Dict[str, Dict[str, Any]] = {}

    with ThreadPoolExecutor(max_workers=max(1, len(collectors))) as executor:
        future_to_collector = {
            executor.submit(c.collect_with_status, profile, dt_start, dt_end, flat_queries): c
            for c in collectors
        }
        for future in as_completed(future_to_collector):
            col = future_to_collector[future]
            try:
                result = future.result()
            except Exception as e:
                result = {"collector": col.name, "status": "failed", "count": 0,
                          "records": [], "errors": [{"collector": col.name,
                          "operation": "orchestration", "error": str(e)}],
                          "warnings": [], "unsupported_reason": None}
            all_records.extend(result["records"])
            stats[col.name] = result["count"]
            collector_results[col.name] = {
                key: result[key] for key in
                ("status", "count", "errors", "warnings", "unsupported_reason")
            }

    statuses = [item["status"] for item in collector_results.values()]
    has_problem = any(s in {"failed", "partially_successful", "unsupported"} for s in statuses)
    has_completed = any(s in {"success", "no_results", "partially_successful"} for s in statuses)
    if has_problem and has_completed:
        collection_status = "partially_successful"
    elif "success" in statuses:
        collection_status = "success"
    elif statuses and all(s == "no_results" for s in statuses):
        collection_status = "no_results"
    elif statuses and all(s == "unsupported" for s in statuses):
        collection_status = "unsupported"
    elif statuses:
        collection_status = "failed"
    else:
        collection_status = "no_results"
    errors = [error for item in collector_results.values() for error in item["errors"]]

    logger.info(f"Pipeline finished. Total raw records discovered: {len(all_records)}")

    # 6. Format return payload for Group 2 & Group 4
    return {
        "equity_profile": profile.to_dict(),
        "raw_articles": all_records,
        "status": {"success": "SUCCESS", "no_results": "NO_ARTICLES",
                    "partially_successful": "PARTIAL_FAILURE", "failed": "FAILED",
                    "unsupported": "UNSUPPORTED"}[collection_status],
        "collection_status": collection_status,
        "collector_stats": stats,
        "collector_results": collector_results,
        "errors": errors,
        "total_articles": len(all_records),
        "query_categories": query_gen.generate(profile),
        "collection_run": {"run_id": run_id, "started_at": started_at,
                           "completed_at": get_current_utc_iso(), "status": collection_status,
                           "start_date": dt_start.isoformat(), "end_date": dt_end.isoformat()}
    }


if __name__ == "__main__":
    import json
    result = collect_equity_news("Reliance")
    print("\n--- PIPELINE EXECUTION RESULT ---")
    print(f"Status: {result.get('status')}")
    print(f"Equity: {result.get('equity_profile', {}).get('company_name')} ({result.get('equity_profile', {}).get('ticker')})")
    print(f"Collector Stats: {result.get('collector_stats')}")
    print(f"Total Discovered: {result.get('total_articles')}")
    if result.get("raw_articles"):
        print("\nSample Discovered Record #1:")
        print(json.dumps(result["raw_articles"][0], indent=2))
