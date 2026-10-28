"""
profile.py - Canonical Equity Profile Data Model

Responsibilities:
- Stores canonical company name, primary ticker, and exchange.
- Maintains company aliases and abbreviations (e.g., RIL, TaMo).
- Tracks major subsidiaries / business divisions (e.g., Jio Platforms, Jaguar Land Rover).
- Serializes cleanly to dictionary / JSON for downstream consumption.
"""

from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field


class EquityProfile(BaseModel):
    """
    Canonical representation of a publicly listed equity.
    Produced by EquityResolver and consumed by QueryGenerator and Collectors.
    """
    company_name: str = Field(..., description="Canonical registered company name, e.g. 'Reliance Industries Limited'")
    ticker: str = Field(..., description="Primary trading symbol, e.g. 'RELIANCE'")
    exchange: str = Field(default="NSE", description="Primary exchange, e.g. 'NSE' or 'BSE'")
    country: str = Field(default="India", description="Country of primary listing")
    isin: Optional[str] = Field(default=None, description="ISIN number, e.g. 'INE002A01018'")
    
    aliases: List[str] = Field(
        default_factory=list,
        description="Known brand names, abbreviations, and informal names, e.g. ['RIL', 'Reliance Industries']"
    )
    
    important_businesses: List[str] = Field(
        default_factory=list,
        description="Key subsidiaries or operating divisions, e.g. ['Jio Platforms', 'Reliance Retail']"
    )

    def to_dict(self) -> Dict[str, Any]:
        """Convert profile to standard dictionary representation."""
        return self.model_dump()
