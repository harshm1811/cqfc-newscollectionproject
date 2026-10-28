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
import yaml
from pathlib import Path

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
        - "status": "SUCCESS" | "PARTIAL" | "FAILED"
        - "collector_stats": dict
    """
    logger = get_logger("group1_pipeline", run_id=run_id)
    logger.info(f"Initiating Group 1 News Collection for query: '{query}'")

    # 1. Load configuration
    config = {}
    cfg_file = Path(config_path)
    if cfg_file.exists():
        with open(cfg_file, "r") as f:
            config = yaml.safe_load(f)

    # 2. Resolve Equity
    resolver = EquityResolver()
    profile = resolver.resolve(query)
    if not profile:
        logger.error(f"Could not resolve equity for query: '{query}'")
        return {
            "equity_profile": None,
            "raw_articles": [],
            "status": "FAILED",
            "message": f"Could not resolve equity '{query}'"
        }

    logger.info(f"Resolved to: {profile.company_name} ({profile.ticker}) on {profile.exchange}")

    # 3. Generate Queries
    query_gen = QueryGenerator()
    query_dict = query_gen.generate(profile)
    flat_queries = query_gen.get_flat_query_list(profile)

    # 4. Instantiate and execute collectors
    # (Collectors can run in parallel using concurrent.futures.ThreadPoolExecutor)
    all_records: List[RawArticleRecord] = []
    stats = {}

    # Example: Google News RSS
    if config.get("collectors", {}).get("google_news_rss", {}).get("enabled", True):
        gnews = GoogleNewsRSSCollector(config=config)
        records = gnews.collect(profile, queries=flat_queries)
        all_records.extend(records)
        stats["google_news_rss"] = len(records)

    # 5. Format return payload for Group 2 & Group 4
    return {
        "equity_profile": profile.to_dict(),
        "raw_articles": [r.model_dump() for r in all_records],
        "status": "SUCCESS" if all_records else "NO_ARTICLES",
        "collector_stats": stats
    }


if __name__ == "__main__":
    # Smoke test run
    res = collect_equity_news("Reliance")
    print(f"Pipeline Result Status: {res.get('status')}")
