"""
logger.py - Standardized Logging for Group 1

Responsibilities:
- Provide structured logs across all collectors and equity modules.
- Formats messages with timestamp, module name, severity, and optional run_id.
- Ensures all collection failures are logged cleanly without silent swallowing.
"""

import logging
import sys
from typing import Optional


def get_logger(name: str, run_id: Optional[str] = None) -> logging.Logger:
    """
    Returns a configured logger instance with standard formatting.
    
    Args:
        name: Name of the module/collector calling the logger.
        run_id: Optional UUID from Group 4 orchestrator to trace runs.
    """
    logger = logging.getLogger(name)
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        handler = logging.StreamHandler(sys.stdout)
        
        prefix = f"[{run_id}] " if run_id else ""
        formatter = logging.Formatter(
            f"%(asctime)s - %(name)s - %(levelname)s - {prefix}%(message)s",
            datefmt="%Y-%m-%d %H:%M:%S"
        )
        handler.setFormatter(formatter)
        logger.addHandler(handler)
        
    return logger
