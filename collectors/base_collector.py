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
from datetime import datetime, timezone
import json
from pathlib import Path
from uuid import uuid4
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
    raw_url: Optional[str] = None        # Original collector URL before redirect resolution


class BaseCollector(ABC):
    """
    Abstract interface that all news and filing collectors must inherit from.
    """

    def __init__(self, name: str, raw_data_dir: str = "data/raw", config: Optional[Dict[str, Any]] = None):
        self.name = name
        self.raw_data_dir = Path(raw_data_dir)
        self.config = config or {}
        self.logger = get_logger(f"collector.{name}")
        self._errors: List[Dict[str, str]] = []
        self._warnings: List[str] = []
        self._unsupported_reason: Optional[str] = None

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

    def record_error(self, operation: str, error: BaseException | str) -> None:
        """Keep actionable per-source failure details for the pipeline result."""
        detail = {"collector": self.name, "operation": operation, "error": str(error)}
        self._errors.append(detail)
        self.logger.warning("%s failed: %s", operation, error)

    def mark_unsupported(self, reason: str) -> None:
        self._unsupported_reason = reason

    @staticmethod
    def _utc(value: datetime) -> datetime:
        if value.tzinfo is None:
            # Naive integration windows are interpreted as UTC; collector publication
            # timestamps are normalized separately by timestamp_parser.
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def collect_with_status(
        self,
        profile: EquityProfile,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None,
        queries: Optional[List[str]] = None,
    ) -> Dict[str, Any]:
        """Run a collector and return records plus explicit success/failure state."""
        self._errors = []
        self._warnings = []
        self._unsupported_reason = None
        try:
            records = self.collect(profile, start_date, end_date, queries)
        except Exception as exc:
            self.record_error("collect", exc)
            records = []

        records = list(records or [])
        if start_date is not None or end_date is not None:
            lower = self._utc(start_date) if start_date is not None else None
            upper = self._utc(end_date) if end_date is not None else None
            kept = []
            for record in records:
                if not record.published_at:
                    self._warnings.append(
                        f"Excluded undated record '{record.title}' because a date window was requested"
                    )
                    continue
                try:
                    published = datetime.fromisoformat(record.published_at.replace("Z", "+00:00"))
                    published = self._utc(published)
                except (TypeError, ValueError):
                    self._warnings.append(
                        f"Excluded record '{record.title}' with an invalid published_at value"
                    )
                    continue
                if (lower is None or published >= lower) and (upper is None or published <= upper):
                    kept.append(record)
            records = kept

        if records and self._errors:
            status = "partially_successful"
        elif self._errors:
            status = "failed"
        elif self._unsupported_reason:
            status = "unsupported"
        elif records:
            status = "success"
        else:
            status = "no_results"
        return {
            "collector": self.name,
            "status": status,
            "count": len(records),
            "records": [record.model_dump() for record in records],
            "errors": list(self._errors),
            "warnings": list(self._warnings),
            "unsupported_reason": self._unsupported_reason,
        }

    def save_raw_payload(self, ticker: str, payload: Any, identifier: str = "raw") -> str:
        """
        Preserve original raw unedited payload to data/raw/{ticker}/.
        """
        try:
            timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S_%f")
            target_dir = self.raw_data_dir / ticker.upper()
            target_dir.mkdir(parents=True, exist_ok=True)
            
            filepath = target_dir / f"{timestamp}_{self.name}_{identifier}_{uuid4().hex[:8]}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                if isinstance(payload, (dict, list)):
                    json.dump(payload, f, indent=2, ensure_ascii=False)
                else:
                    f.write(str(payload))
            return str(filepath)
        except Exception as e:
            self.record_error("save_raw_payload", e)
            return ""
