"""
updated_relevance.py - Root relevance scoring module for backward compatibility and Member 2 scoring.
"""

import json
from pathlib import Path
from typing import Any, Dict, Optional, Union

from processing.relevance import RelevanceEngine, calculate_relevance_score as _calc_rel


def calculate_record_equity_relevance(
    news_record: Dict[str, Any],
    company_profile: Dict[str, Union[str, list]],
) -> float:
    """Score one already-loaded article using RelevanceEngine."""
    engine = RelevanceEngine()
    return engine.score_record(news_record, company_profile)


def calculate_relevance_score(news_record: Dict[str, Any], company_profile: Optional[Dict[str, Any]] = None) -> float:
    """Stable public name for the Group 2 -> Group 3 schema."""
    engine = RelevanceEngine()
    return engine.score_record(news_record, company_profile)


def calculate_file_equity_relevance(
    file_input: Union[str, Path],
    company_profile: Dict[str, Union[str, list]],
) -> float:
    """Reads a news record from a JSON or CSV file and calculates equity relevance score."""
    file_path = Path(file_input)
    if not file_path.exists():
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            news_record = data[0] if isinstance(data, list) else data
    elif suffix == ".csv":
        import pandas as pd
        df = pd.read_csv(file_path)
        if df.empty:
            return 0.0
        news_record = df.iloc[0].to_dict()
    else:
        raise ValueError("Unsupported file format. Please provide a .json or .csv file.")

    return calculate_record_equity_relevance(news_record, company_profile)
