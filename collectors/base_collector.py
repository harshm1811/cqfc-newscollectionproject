"""
base_collector.py - Abstract Base Class for All Group 1 Collectors

CRITICAL REQUIREMENTS:
1. Standard Collector Output Schema:
   All collectors MUST emit instances of RawArticleRecord (or dict matching schema):
   {
       "company_name": "...",
       "ticker": "...",
       "title": "...",
       "description": "...",
       "url": "...",
       "source": "...",
       "source_type": "...",
       "primary_source": false,
       "published_at": "...",
       "first_seen_at": "...",
       "retrieved_at": "...",
       "collector": "..."
   }

2. Raw Data Preservation:
   - Dumps raw unmodified API responses / XML / JSON to data/raw/{ticker}/{timestamp}_{collector}.json
   - NEVER overwrite or clean raw data.

3. Failure Handling:
   - Collection errors MUST NOT crash the pipeline.
   - Failures must be logged and reported via run tracking.
"""

from abc import ABC, abstractmethod
from typing import List, Dict, Any, Optional
from datetime import datetime
import json
import os
from pathlib import Path
from pydantic import BaseModel, Field

from equity.profile import EquityProfile
from utils.logger import get_logger
from utils.timestamp_parser import get_current_utc_iso


class RawArticleRecord(BaseModel):
    """
    Standardized Raw Article Schema: Group 1 -> Group 2 Contract.
    """
    company_name: str
    ticker: str
    title: str
    description: Optional[str] = ""
    url: str
    source: str
    source_type: str  # EXCHANGE_FILING, REGULATORY, COMPANY_IR, NEWS_RSS, AGGREGATOR
    primary_source: bool = False
    published_at: Optional[str] = None  # ISO-8601 UTC or None
    first_seen_at: str                  # ISO-8601 UTC
    retrieved_at: str                   # ISO-8601 UTC
    collector: str


class BaseCollector(ABC):
    """
    Abstract interface that all news and filing collectors must inherit from.
    """

    def __init__(self, name: str, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.raw_data_dir = Path(raw_data_dir)
        self.config = config or {}
        self.logger = get_logger(f"collector.{name}")

    @abstractmethod
    def collect(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None
    ) -> List[RawArticleRecord]:
        """
        Execute collection for a canonical equity profile.
        
        Args:
            profile: Canonical EquityProfile
            start_date: Earliest date to look back
            end_date: Latest date
            queries: Generated queries to search (for search-driven collectors)
            
        Returns:
            List of RawArticleRecord instances. Must return empty list on failure, never raise unhandled exceptions.
        """
        pass

    def save_raw_payload(self, ticker: str, payload: Any, identifier: str = "raw") -> str:
        """
        Preserve original raw unedited payload to data/raw/{ticker}/.
        """
        try:
            timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
            target_dir = self.raw_data_dir / ticker.upper()
            target_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = target_dir / f"{timestamp}_{self.name}_{identifier}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                if isinstance(payload, (dict, list)):
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                else:
                    f.write(str(payload))
            return str(filepath)
        except Exception as e:
            self.logger.error(f"Failed to save raw payload for {ticker}: {e}")
            return ""
