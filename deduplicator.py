"""Exact article deduplication and cautious source-independence notes.

Input: the team's JSON object with an ``articles`` list (or a plain list).
All fields from each input article are copied through unchanged. This module
adds ``deduplication`` metadata and emits one representative per exact group.
"""

import argparse
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import re
from urllib.parse import urlsplit, urlunsplit


def normalized_url(value):
    """Make URL comparisons stable while retaining article-identifying data."""
    if not isinstance(value, str) or not value.strip():
        return ""
    try:
        parts = urlsplit(value.strip())
        host = parts.netloc.lower()
        path = re.sub(r"/{2,}", "/", parts.path).rstrip("/")
        tracking = {"gclid", "fbclid", "mc_cid", "mc_eid"}
        kept_query = []
        for segment in parts.query.split("&"):
            key = segment.split("=", 1)[0].lower()
            if key.startswith("utm_") or key in tracking:
                continue
            if segment:
                kept_query.append(segment)
        return urlunsplit((parts.scheme.lower(), host, path, "&".join(kept_query), ""))
    except ValueError:
        return value.strip().casefold()


def normalized_title(value):
    """Normalize case and punctuation for exact-title comparisons."""
    if not isinstance(value, str):
        return ""
    return " ".join(re.findall(r"\w+", value.casefold()))


def _source(article):
    return str(article.get("source") or "").strip()


def _source_kind(article):
    return str(article.get("source_type") or "").upper()


def _independence_note(group):
    """Estimate independent evidence conservatively; never infer syndication as fact."""
    source_names = { _source(article).casefold() for article in group if _source(article) }
    publisher_domains = set()
    for article in group:
        try:
            host = urlsplit(str(article.get("url") or "")).hostname
            if host:
                publisher_domains.add(host.lower().removeprefix("www."))
        except ValueError:
            pass

    syndicated_hint = (
        len(group) > 1
        and len(publisher_domains) > 1
        and all(_source_kind(article) in {"NEWS_RSS", "AGGREGATOR"} for article in group)
    )
    if syndicated_hint:
        return {
            "distinct_sources_observed": len(source_names),
            "independent_evidence_count": 1,
            "status": "possible_syndication",
            "note": "Exact copies from multiple news sources are conservatively counted as one evidence item; syndication is only a possibility.",
        }
    return {
        "distinct_sources_observed": len(source_names),
        "independent_evidence_count": 1,
        "status": "single_evidence_item",
        "note": "Exact duplicate records are one evidence item. This does not determine whether distinct non-duplicate reporting is independent.",
    }


def _cluster_id(group, match_type):
    """Return a deterministic ID shared by every record in an exact group."""
    urls = sorted({normalized_url(item.get("url")) for item in group if normalized_url(item.get("url"))})
    titles = sorted({normalized_title(item.get("title")) for item in group if normalized_title(item.get("title"))})
    if match_type in {"url", "url_and_title"} and urls:
        identity = "url:" + urls[0]
    elif titles:
        identity = "title:" + titles[0]
    else:
        identity = "records:" + "|".join(sorted(str(item.get("article_id") or "") for item in group))
    return "CLUSTER_" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:12].upper()


def deduplicate_articles(articles):
    """Return a result object with exact duplicate groups and preserved provenance.

    A match by either normalized URL or normalized title puts records together.
    Missing URL/title values are ignored.
    """
    records = [deepcopy(article) for article in articles]
    parents = list(range(len(records)))

    def find(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def join(left, right):
        left_root, right_root = find(left), find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    seen = {"url": {}, "title": {}}
    for index, article in enumerate(records):
        for kind, key in (("url", normalized_url(article.get("url"))),
                          ("title", normalized_title(article.get("title")))):
            if key:
                if key in seen[kind]:
                    join(index, seen[kind][key])
                else:
                    seen[kind][key] = index

    groups = {}
    for index in range(len(records)):
        groups.setdefault(find(index), []).append(index)

    output = []
    duplicate_group_count = 0
    for member_indexes in groups.values():
        group_records = [records[index] for index in member_indexes]
        is_duplicate_group = len(group_records) > 1
        duplicate_group_count += int(is_duplicate_group)
        match_type = "none"
        if is_duplicate_group:
            urls = [normalized_url(item.get("url")) for item in group_records]
            titles = [normalized_title(item.get("title")) for item in group_records]
            match_type = "url_and_title" if len(set(urls)) == 1 and len(set(titles)) == 1 else (
                "url" if len(set(urls)) == 1 else "title"
            )

        cluster_id = _cluster_id(group_records, match_type)
        for item in group_records:
            item["duplicate_cluster_id"] = cluster_id
            if "primary_source" not in item:
                is_prim = _source_kind(item) in {"EXCHANGE_FILING", "REGULATORY_ANNOUNCEMENT", "COMPANY_IR"}
                item["primary_source"] = is_prim

        canonical = deepcopy(group_records[0])
        canonical["independent_source"] = True
        canonical["primary_source"] = bool(canonical.get("primary_source", False))
        canonical["deduplication"] = {
            "group_size": len(group_records),
            "is_exact_duplicate": is_duplicate_group,
            "matched_by": match_type,
            "source_independence": _independence_note(group_records),
            "near_duplicate_review": "not_assessed; no records were merged based on approximate similarity",
        }
        if is_duplicate_group:
            for item in group_records[1:]:
                dup_copy = deepcopy(item)
                dup_copy["independent_source"] = False
                dup_copy["primary_source"] = bool(dup_copy.get("primary_source", False))
                if "duplicate_records" not in canonical:
                    canonical["duplicate_records"] = []
                canonical["duplicate_records"].append(dup_copy)
        output.append(canonical)

    return {
        "record_count": len(output),
        "input_record_count": len(records),
        "duplicate_group_count": duplicate_group_count,
        "articles": output,
    }


def main():
    parser = argparse.ArgumentParser(description="Deduplicate article JSON records.")
    parser.add_argument("input", nargs="?", default="cleaned_articles.json")
    parser.add_argument("output", nargs="?", default="deduplicated_articles.json")
    args = parser.parse_args()
    with Path(args.input).open(encoding="utf-8") as file:
        data = json.load(file)
    articles = data.get("articles") if isinstance(data, dict) else data
    if not isinstance(articles, list) or not all(isinstance(item, dict) for item in articles):
        raise ValueError("Input must be a list of article objects or an object with an 'articles' list.")
    result = deduplicate_articles(articles)
    with Path(args.output).open("w", encoding="utf-8") as file:
        json.dump(result, file, indent=2, ensure_ascii=False)
        file.write("\n")
    print(f"Saved {result['record_count']} unique records from {result['input_record_count']} inputs to {args.output}")


if __name__ == "__main__":
    main()
