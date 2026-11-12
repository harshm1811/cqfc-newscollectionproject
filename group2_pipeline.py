"""Run Member 1 cleaning, Member 2 scoring, then Member 3 deduplication."""

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any, Dict, List

from cleaner import clean_article_text
from deduplicator import deduplicate_articles
from normalizer import normalize_articles
from updated_relevance import calculate_relevance_score


REQUIRED_OUTPUT_FIELDS = (
    "article_id", "ticker", "title", "clean_text", "source", "source_type",
    "published_at", "first_seen_at", "relevance_score", "duplicate_cluster_id",
    "primary_source", "independent_source",
)


def _article_id(article):
    """Stable ID from normalized URL, falling back to ticker and title."""
    url = article.get("url")
    identity = str(url).strip().casefold() if url else ""
    if not identity:
        identity = "|".join((str(article.get("ticker") or "").casefold(),
                             " ".join(str(article.get("title") or "").casefold().split())))
    return "ARTICLE_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()


def validate_output(articles: List[Dict[str, Any]]) -> None:
    """Raise a clear error if a final article misses the agreed Group 3 schema."""
    problems = []
    for index, article in enumerate(articles):
        missing = [field for field in REQUIRED_OUTPUT_FIELDS if field not in article]
        if missing:
            problems.append(f"article {index}: missing {', '.join(missing)}")
        score = article.get("relevance_score")
        if not isinstance(score, (int, float)) or not 0 <= score <= 1:
            problems.append(f"article {index}: relevance_score must be between 0 and 1")
    ids = [article.get("article_id") for article in articles]
    if len(ids) != len(set(ids)):
        problems.append("article_id values must be unique")
    if problems:
        raise ValueError("Final schema validation failed: " + "; ".join(problems))


def run_pipeline(input_path, output_path, min_relevance_threshold=None):
    with Path(input_path).open("r", encoding="utf-8") as file:
        data = json.load(file)

    # Accept a raw list or Member 1's {"record_count": ..., "articles": [...]} output.
    articles = data.get("articles") if isinstance(data, dict) else data
    if not isinstance(articles, list) or not all(isinstance(row, dict) for row in articles):
        raise ValueError("Input JSON must be a list of article objects or contain an 'articles' list.")

    # Member 1's normalizer adds these two fields to every article. Detect that
    # output and avoid replacing its original_record with a copy of itself.
    already_cleaned = (
        isinstance(data, dict)
        and "record_count" in data
        and bool(articles)
        and all("original_record" in row and "validation_flags" in row for row in articles)
    )
    if already_cleaned:
        ready_articles = articles
        steps = ["use_member1_cleaned_input", "score_relevance", "deduplicate"]
    else:
        ready_articles = normalize_articles(articles)
        steps = ["clean_and_normalize", "score_relevance", "deduplicate"]

    scored = []
    for article in ready_articles:
        profile = {
            "name": article.get("company_name", ""),
            "ticker": article.get("ticker", ""),
            "subsidiaries": article.get("subsidiaries", []),
        }
        if "article_id" not in article or not article["article_id"]:
            article["article_id"] = _article_id(article)
        article["relevance_score"] = calculate_relevance_score(article, profile)
        article.pop("equity_relevance_score", None)
        scored.append(article)

    # Optional relevance filtering if threshold is specified
    if min_relevance_threshold is not None:
        scored = [a for a in scored if a["relevance_score"] >= min_relevance_threshold]

    result = deduplicate_articles(scored)

    # Guarantee top-level fields for Group 3 compatibility
    for art in result["articles"]:
        if "primary_source" not in art:
            art["primary_source"] = str(art.get("source_type") or "").upper() in {
                "EXCHANGE_FILING", "REGULATORY_ANNOUNCEMENT", "COMPANY_IR"
            }
        if "independent_source" not in art:
            art["independent_source"] = True

    validate_output(result["articles"])
    result["pipeline_steps"] = steps
    with Path(output_path).open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)
        file.write("\n")
    return result


def main():
    parser = argparse.ArgumentParser(description="Run the Group 2 article-processing pipeline.")
    parser.add_argument("input", nargs="?", default="mock_raw_articles.json")
    parser.add_argument("output", nargs="?", default="final_articles.json")
    parser.add_argument("--min-relevance", type=float, default=None, help="Optional minimum relevance threshold filter")
    args = parser.parse_args()
    result = run_pipeline(args.input, args.output, min_relevance_threshold=args.min_relevance)
    print(f"Saved {result['record_count']} unique articles from {result['input_record_count']} input records to {args.output}")


if __name__ == "__main__":
    main()
