"""
collectors package initialization.
Exposes BaseCollector and concrete collector implementations.
"""

from .base_collector import BaseCollector, RawArticleRecord
from .google_news_rss import GoogleNewsRSSCollector
from .generic_rss_collector import GenericRSSCollector
from .nse_collector import NSECollector
from .bse_collector import BSECollector
from .sebi_collector import SEBICollector
from .company_ir_collector import CompanyIRCollector

__all__ = [
    "BaseCollector",
    "RawArticleRecord",
    "GoogleNewsRSSCollector",
    "GenericRSSCollector",
    "NSECollector",
    "BSECollector",
    "SEBICollector",
    "CompanyIRCollector"
]
