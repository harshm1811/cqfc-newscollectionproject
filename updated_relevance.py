import json
import re
from pathlib import Path
from typing import Dict, Union


def calculate_record_equity_relevance(
    news_record: Dict[str, object],
    company_profile: Dict[str, Union[str, list]],
) -> float:
    """Score one already-loaded article, including Member 1's description field."""
    title = str(news_record.get("title") or "").lower()
    content = str(
        news_record.get("content")
        or news_record.get("summary")
        or news_record.get("description")
        or ""
    ).lower()

    name = str(company_profile.get("name") or "").lower()
    ticker = str(company_profile.get("ticker") or "").lower()
    subsidiaries = [str(sub).lower() for sub in (company_profile.get("subsidiaries") or [])]

    score = 0.0
    if ticker:
        if re.search(rf"\b{re.escape(ticker)}\b", title):
            score = max(score, 0.85)
        elif re.search(rf"\b{re.escape(ticker)}\b", content):
            score = max(score, 0.5)
    if name:
        if re.search(rf"\b{re.escape(name)}\b", title):
            score = max(score, 1.0)
        elif re.search(rf"\b{re.escape(name)}\b", content):
            score = max(score, 0.7)
    for subsidiary in subsidiaries:
        if not subsidiary:
            continue
        if re.search(rf"\b{re.escape(subsidiary)}\b", title):
            score = max(score, 0.8)
            break
        if re.search(rf"\b{re.escape(subsidiary)}\b", content):
            score = max(score, 0.5)
            break
    return round(float(min(max(score, 0.0), 1.0)), 2)


# Stable public name for the Group 2 → Group 3 schema. Keep the original
# function name above for compatibility with existing callers.
def calculate_relevance_score(news_record, company_profile):
    return calculate_record_equity_relevance(news_record, company_profile)

def calculate_file_equity_relevance(
    file_input: Union[str, Path], 
    company_profile: Dict[str, Union[str, list]]
) -> float:
    """
    Reads a news record from a JSON or CSV file and calculates 
    its equity relevance score (0.0 to 1.0).

    Parameters:
    - file_input (str or Path): Path to the JSON or CSV file containing news data.
    - company_profile (dict): Company metadata (name, ticker, subsidiaries).

    Returns:
    - float: Relevance score between 0.0 and 1.0.
    """
    file_path = Path(file_input)
    
    if not file_path.exists():
        raise FileNotFoundError(f"The file {file_path} does not exist.")

    # 1. Parse file based on extension
    suffix = file_path.suffix.lower()
    if suffix == ".json":
        with open(file_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            # Handle if JSON is a single dict or a list of records (taking the first one)
            news_record = data[0] if isinstance(data, list) else data
            
    elif suffix == ".csv":
        import pandas as pd
        df = pd.read_csv(file_path)
        if df.empty:
            return 0.0
        # Take the first row as the news record
        news_record = df.iloc[0].to_dict()
    else:
        raise ValueError("Unsupported file format. Please provide a .json or .csv file.")

    # 2. Extract and normalize text fields from the record
    title = str(news_record.get("title", "")).lower()
    content = str(news_record.get("content", news_record.get("summary", ""))).lower()
    
    name = company_profile.get("name", "").lower()
    ticker = company_profile.get("ticker", "").lower()
    subsidiaries = [sub.lower() for sub in company_profile.get("subsidiaries", [])]
    
    score = 0.0
    
    # 3. Apply Scoring Logic
    # Check Ticker
    if ticker:
        if re.search(rf"\b{re.escape(ticker)}\b", title):
            score = max(score, 0.85)
        elif re.search(rf"\b{re.escape(ticker)}\b", content):
            score = max(score, 0.5)
            
    # Check Main Company Name
    if name:
        if re.search(rf"\b{re.escape(name)}\b", title):
            score = max(score, 1.0)
        elif re.search(rf"\b{re.escape(name)}\b", content):
            score = max(score, 0.7)
            
    # Check Subsidiaries (Crucial for indirect hits like Jio -> Reliance)
    for sub in subsidiaries:
        if re.search(rf"\b{re.escape(sub)}\b", title):
            score = max(score, 0.8)
            break
        elif re.search(rf"\b{re.escape(sub)}\b", content):
            score = max(score, 0.5)
            break
            
    return round(float(min(max(score, 0.0), 1.0)), 2)
