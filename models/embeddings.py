"""
models/embeddings.py - Semantic text embeddings and similarity calculation.

Uses SentenceTransformers when available, with a robust zero-dependency
TF-IDF / character-word n-gram vectorizer fallback for standalone environments.
"""

from __future__ import annotations

import math
import hashlib
from functools import lru_cache
import re
from typing import List, Sequence, Union
import numpy as np

# Try importing sentence_transformers
_HAS_ST = False
try:
    from sentence_transformers import SentenceTransformer
    _HAS_ST = True
except Exception:
    _HAS_ST = False


@lru_cache(maxsize=2)
def _load_sentence_transformer(model_name: str):
    """Reuse one loaded embedding model across pipeline instances in a process."""
    return SentenceTransformer(model_name)

STOP_WORDS = {
    "a", "an", "the", "in", "on", "at", "to", "for", "of", "and", "or",
    "is", "was", "are", "were", "be", "been", "by", "with", "from", "as",
    "it", "its", "that", "this", "than", "into", "about",
}


def cosine_similarity(v1: np.ndarray, v2: np.ndarray) -> float:
    """Compute cosine similarity between two 1D vectors."""
    norm1 = np.linalg.norm(v1)
    norm2 = np.linalg.norm(v2)
    if norm1 == 0 or norm2 == 0:
        return 0.0
    return float(np.dot(v1, v2) / (norm1 * norm2))


class FallbackTfidfEmbedder:
    """
    Lightweight, deterministic word & subword n-gram embedding fallback.
    Produces dense semantic vectors without external models or paid APIs.
    """

    def __init__(self, dim: int = 512):
        self.dim = dim

    def _tokenize(self, text: str) -> List[str]:
        words = [w for w in re.findall(r"\w+", text.lower()) if w not in STOP_WORDS]
        tokens = list(words)
        # Add character tri-grams to capture stem & morphology similarity
        for word in words:
            if len(word) >= 3:
                for i in range(len(word) - 2):
                    tokens.append(word[i:i+3])
        return tokens

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        vectors = []
        for text in texts:
            vec = np.zeros(self.dim, dtype=np.float32)
            tokens = self._tokenize(text)
            if not tokens:
                vectors.append(vec)
                continue
            for tok in tokens:
                # Deterministic feature hashing
                digest = hashlib.blake2b(tok.encode("utf-8"), digest_size=8).digest()
                h = int.from_bytes(digest, "big") % self.dim
                vec[h] += 1.0
            norm = np.linalg.norm(vec)
            if norm > 0:
                vec /= norm
            vectors.append(vec)
        return np.array(vectors)


class EmbeddingModel:
    """
    Unified embedding interface.
    Attempts to load local SentenceTransformer ('all-MiniLM-L6-v2');
    gracefully uses FallbackTfidfEmbedder if unavailable.
    """

    def __init__(self, model_name: str = "all-MiniLM-L6-v2", force_fallback: bool = False):
        self.model_name = model_name
        self.backend = "fallback"
        self._st_model = None

        if _HAS_ST and not force_fallback:
            try:
                self._st_model = _load_sentence_transformer(model_name)
                self.backend = "sentence_transformers"
            except Exception:
                self._fallback = FallbackTfidfEmbedder()
        else:
            self._fallback = FallbackTfidfEmbedder()

    def encode(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.empty((0, 512), dtype=np.float32)

        if self.backend == "sentence_transformers" and self._st_model is not None:
            embeddings = self._st_model.encode(list(texts), convert_to_numpy=True)
            return embeddings
        else:
            return self._fallback.encode(texts)

    def similarity(self, text1: str, text2: str) -> float:
        """Calculate pairwise cosine similarity between two texts."""
        vecs = self.encode([text1, text2])
        return cosine_similarity(vecs[0], vecs[1])

    def similarity_matrix(self, texts: Sequence[str]) -> np.ndarray:
        """Compute all-pairs cosine similarity matrix."""
        if not texts:
            return np.empty((0, 0))
        vecs = self.encode(texts)
        norms = np.linalg.norm(vecs, axis=1, keepdims=True)
        norms[norms == 0] = 1e-12
        normalized = vecs / norms
        return np.dot(normalized, normalized.T)
