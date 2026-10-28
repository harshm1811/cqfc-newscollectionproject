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
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
import yaml

from equity.resolver import EquityResolver
from equity.query_generator import QueryGenerator
from collectors.google_news_rss import GoogleNewsRSSCollector
from collectors.generic_rss_collector import GenericRSSCollector
from collectors.nse_collector import NSECollector
from collectors.bse_collector import BSECollector
from collectors.sebi_collector import SEBICollector
from collectors.base_collector import RawArticleRecord
from utils.logger import get_logger


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
    logger = get_logger("group1_pipeline", run_id=run_id)
    logger.info(f"Initiating Group 1 News Collection for query: '{query}'")

    # 1. Load configuration
    config = {}
    cfg_file = Path(config_path)
    if cfg_file.exists():
        try:
            with open(cfg_file, "r") as f:
                config = yaml.safe_load(f) or {}
        except Exception as e:
            logger.warning(f"Could not load config file {config_path}: {e}")

    # Parse date arguments if provided
    dt_start = None
    dt_end = None
    if start_date:
        try:
            dt_start = datetime.fromisoformat(start_date.replace("Z", "+00:00"))
        except Exception:
            pass
    if end_date:
        try:
            dt_end = datetime.fromisoformat(end_date.replace("Z", "+00:00"))
        except Exception:
            pass

    # 2. Resolve Equity
    resolver = EquityResolver()
    profile = resolver.resolve(query)
    if not profile:
        logger.error(f"Could not resolve equity for query: '{query}'")
        return {
            "equity_profile": None,
            "raw_articles": [],
            "status": "FAILED",
            "message": f"Could not resolve equity '{query}'",
            "collector_stats": {}
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

    # 5. Execute collectors in parallel
    all_records: List[RawArticleRecord] = []
    stats: Dict[str, int] = {}

    with ThreadPoolExecutor(max_workers=5) as executor:
        future_to_collector = {
            executor.submit(c.collect, profile, dt_start, dt_end, flat_queries): c
            for c in collectors
        }
        for future in as_completed(future_to_collector):
            col = future_to_collector[future]
            try:
                records = future.result()
                all_records.extend(records)
                stats[col.name] = len(records)
            except Exception as e:
                logger.error(f"Collector {col.name} failed unhandled: {e}")
                stats[col.name] = 0

    logger.info(f"Pipeline finished. Total raw records discovered: {len(all_records)}")

    # 6. Format return payload for Group 2 & Group 4
    return {
        "equity_profile": profile.to_dict(),
        "raw_articles": [r.model_dump() for r in all_records],
        "status": "SUCCESS" if all_records else "NO_ARTICLES",
        "collector_stats": stats,
        "total_articles": len(all_records)
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
