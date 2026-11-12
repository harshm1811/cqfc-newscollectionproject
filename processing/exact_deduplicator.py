"""
processing/exact_deduplicator.py - High-precision exact article deduplication.

Detects exact duplicates using:
- Canonical URL
- Normalized headline
- Content Hash (SHA-256 of normalized text)
Maintains cluster IDs and retains original duplicate records for provenance.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
import re
from typing import Any, Dict, List, Optional, Sequence, Tuple
from urllib.parse import urlsplit, urlunsplit

from .normalizer import normalize_url


def normalized_title(title: Optional[str]) -> str:
    """Normalize headline for exact comparison: lowercase, strip punctuation, collapse whitespace."""
    if not title or not isinstance(title, str):
        return ""
    words = re.findall(r"\w+", title.lower())
    return " ".join(words)


def content_hash(text: Optional[str]) -> str:
    """Compute SHA-256 hash of normalized text."""
    if not text or not isinstance(text, str):
        return ""
    cleaned = " ".join(re.findall(r"\w+", text.lower()))
    if not cleaned:
        return ""
    return hashlib.sha256(cleaned.encode("utf-8")).hexdigest()[:16]


def make_cluster_id(group: List[Dict[str, Any]], match_type: str = "exact") -> str:
    """Deterministic cluster ID shared by every record in an exact group."""
    urls = sorted({normalize_url(item.get("url")) for item in group if normalize_url(item.get("url"))})
    titles = sorted({normalized_title(item.get("title")) for item in group if normalized_title(item.get("title"))})
    hashes = sorted({content_hash(item.get("clean_text") or item.get("description")) for item in group if item.get("clean_text") or item.get("description")})

    if urls:
        identity = f"url:{urls[0]}"
    elif titles:
        identity = f"title:{titles[0]}"
    elif hashes:
        identity = f"hash:{hashes[0]}"
    else:
        identity = f"records:{group[0].get('article_id', 'unknown')}"

    return "CLUST-" + hashlib.sha256(identity.encode("utf-8")).hexdigest()[:10].upper()


class ExactDeduplicator:
    """Clusters exact duplicate articles across URLs, titles, and content hashes."""

    def deduplicate(self, articles: Sequence[Dict[str, Any]]) -> Dict[str, Any]:
        records = [deepcopy(a) for a in articles]
        n = len(records)
        if n == 0:
            return {"record_count": 0, "input_record_count": 0, "duplicate_group_count": 0, "articles": []}

        parents = list(range(n))

        def find(i: int) -> int:
            while parents[i] != i:
                parents[i] = parents[parents[i]]
                i = parents[i]
            return i

        def union(i: int, j: int) -> None:
            root_i, root_j = find(i), find(j)
            if root_i != root_j:
                parents[root_j] = root_i

        seen_urls: Dict[str, int] = {}
        seen_titles: Dict[str, int] = {}
        seen_hashes: Dict[str, int] = {}

        for idx, art in enumerate(records):
            u = normalize_url(art.get("url"))
            t = normalized_title(art.get("title"))
            h = content_hash(art.get("clean_text") or art.get("description"))

            if u:
                if u in seen_urls:
                    union(idx, seen_urls[u])
                else:
                    seen_urls[u] = idx

            if t:
                if t in seen_titles:
                    union(idx, seen_titles[t])
                else:
                    seen_titles[t] = idx

            if h and len(h) >= 10:
                if h in seen_hashes:
                    union(idx, seen_hashes[h])
                else:
                    seen_hashes[h] = idx

        groups: Dict[int, List[int]] = {}
        for idx in range(n):
            root = find(idx)
            groups.setdefault(root, []).append(idx)

        unique_articles = []
        duplicate_group_count = 0

        for member_indices in groups.values():
            group = [records[i] for i in member_indices]
            is_dup = len(group) > 1
            if is_dup:
                duplicate_group_count += 1

            # Match criteria detection
            u_set = {normalize_url(x.get("url")) for x in group if normalize_url(x.get("url"))}
            t_set = {normalized_title(x.get("title")) for x in group if normalized_title(x.get("title"))}
            h_set = {content_hash(x.get("clean_text")) for x in group if content_hash(x.get("clean_text"))}

            if len(u_set) == 1 and len(t_set) == 1:
                match_type = "url_and_title"
            elif len(u_set) == 1:
                match_type = "url"
            elif len(t_set) == 1:
                match_type = "title"
            elif len(h_set) == 1:
                match_type = "content_hash"
            else:
                match_type = "composite"

            cluster_id = make_cluster_id(group, match_type)
            for item in group:
                item["duplicate_cluster_id"] = cluster_id

            # Select canonical representative: prefer primary source, or earliest timestamp, or longest text
            canonical = sorted(
                group,
                key=lambda x: (
                    1 if x.get("primary_source") else 0,
                    len(str(x.get("clean_text") or "")),
                ),
                reverse=True,
            )[0]

            # Mark source independence
            sources = {str(x.get("source") or "").lower() for x in group if x.get("source")}
            canonical["independent_source"] = True
            canonical["deduplication"] = {
                "group_size": len(group),
                "is_exact_duplicate": is_dup,
                "matched_by": match_type if is_dup else "none",
                "distinct_sources_observed": len(sources),
            }

            if is_dup:
                # Retain original duplicates
                canonical["duplicate_records"] = [deepcopy(x) for x in group if x != canonical]

            unique_articles.append(canonical)

        return {
            "record_count": len(unique_articles),
            "input_record_count": n,
            "duplicate_group_count": duplicate_group_count,
            "articles": unique_articles,
        }
