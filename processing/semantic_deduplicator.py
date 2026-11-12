"""
processing/semantic_deduplicator.py - Semantic article clustering & source independence engine.

Clusters stories describing the exact same event or reporting the same development,
even when headlines are rephrased or syndicated across different outlets.

Uses SentenceTransformers via models.embeddings.EmbeddingModel with configurable
similarity threshold.
"""

from __future__ import annotations

from copy import deepcopy
import hashlib
from typing import Any, Dict, List, Optional, Sequence
import numpy as np

from models.embeddings import EmbeddingModel
from .exact_deduplicator import normalized_title


def make_semantic_cluster_id(representative_text: str) -> str:
    h = hashlib.sha256(representative_text.encode("utf-8")).hexdigest()[:10].upper()
    return f"CLUST-SEM-{h}"


class SemanticDeduplicator:
    """Clusters semantically equivalent news stories and tags source independence."""

    def __init__(
        self,
        similarity_threshold: float = 0.65,
        embedding_model: Optional[EmbeddingModel] = None,
    ):
        self.similarity_threshold = similarity_threshold
        self.model = embedding_model or EmbeddingModel()

    def cluster_articles(
        self,
        articles: Sequence[Dict[str, Any]],
        threshold: Optional[float] = None,
    ) -> List[Dict[str, Any]]:
        """
        Group semantically near-duplicate stories, assign duplicate_cluster_id,
        and evaluate independent_source flags.
        """
        records = [deepcopy(a) for a in articles]
        n = len(records)
        if n <= 1:
            for art in records:
                if "duplicate_cluster_id" not in art or not art["duplicate_cluster_id"]:
                    art["duplicate_cluster_id"] = "CLUST-" + hashlib.sha256(str(art.get("title")).encode()).hexdigest()[:10].upper()
                if "independent_source" not in art:
                    art["independent_source"] = True
                if "primary_source" not in art:
                    art["primary_source"] = False
            return records

        th = threshold if threshold is not None else self.similarity_threshold

        # Texts for semantic embedding: headline + beginning of text
        texts = []
        for art in records:
            t = art.get("title") or ""
            body = (art.get("clean_text") or art.get("description") or "")[:200]
            texts.append(f"{t}. {body}".strip())

        sim_matrix = self.model.similarity_matrix(texts)

        # Graph connected components
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

        for i in range(n):
            for j in range(i + 1, n):
                # Must be for the same equity ticker
                if str(records[i].get("ticker")).upper() == str(records[j].get("ticker")).upper():
                    if sim_matrix[i, j] >= th:
                        union(i, j)

        groups: Dict[int, List[int]] = {}
        for idx in range(n):
            root = find(idx)
            groups.setdefault(root, []).append(idx)

        clustered_articles = []

        for member_indices in groups.values():
            group = [records[i] for i in member_indices]

            # If multiple records form a semantic cluster
            is_semantic_cluster = len(group) > 1

            # Determine cluster ID: if any item has an existing cluster ID from exact dedup, preserve it
            cluster_id = None
            for item in group:
                if item.get("duplicate_cluster_id") and not item["duplicate_cluster_id"].startswith("CLUST-SEM-"):
                    cluster_id = item["duplicate_cluster_id"]
                    break
            if not cluster_id:
                rep_title = group[0].get("title", "")
                cluster_id = make_semantic_cluster_id(rep_title)

            # Analyze publishers within the cluster to set source independence
            seen_publishers = set()
            for rank, item in enumerate(group):
                item["duplicate_cluster_id"] = cluster_id
                pub = str(item.get("source") or "").lower()
                is_primary = bool(item.get("primary_source", False))

                if is_primary:
                    item["independent_source"] = True
                elif pub not in seen_publishers:
                    # First article seen from this publisher in this event cluster is independent
                    seen_publishers.add(pub)
                    item["independent_source"] = True
                else:
                    # Duplicate story from same publisher or syndicated re-post
                    item["independent_source"] = False

                clustered_articles.append(item)

        return clustered_articles
