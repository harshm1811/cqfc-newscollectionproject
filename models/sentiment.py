"""
models/sentiment.py - Financial sentiment (FinBERT) + event-level aggregation.

* Article level: P(pos), P(neu), P(neg), sentiment_score = P(pos) - P(neg).
* Event level: NOT a plain mean of articles. Syndicated copies of the same
  story would dominate, so each *independent source* gets one vote
  (articles within a source are averaged first), and primary-source articles
  can be given extra weight. Probabilities are averaged and re-normalised,
  then score = P(pos) - P(neg) is recomputed from the aggregate probabilities.

The model is replaceable: implement `SentimentModel.predict_proba_batch`.
"""

from __future__ import annotations

import logging
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from events.event_model import Article, SentimentResult

logger = logging.getLogger("models.sentiment")


class SentimentModel(ABC):
    name: str = "base"

    @abstractmethod
    def predict_proba_batch(self, texts: Sequence[str]) -> List[Tuple[float, float, float]]:
        """Return (P_pos, P_neu, P_neg) for each text."""

    def analyze(self, texts: Sequence[str]) -> List[SentimentResult]:
        return [SentimentResult.from_probs(p, n, g, self.name)
                for p, n, g in self.predict_proba_batch(list(texts))]


class FinBERTSentimentModel(SentimentModel):
    """
    Local ProsusAI/finbert via HuggingFace transformers.
    Weights download once, then can run fully offline (local_files_only=True).
    Requires: pip install transformers torch
    """

    def __init__(self, model_name: str = "ProsusAI/finbert", device: Optional[int] = None,
                 batch_size: int = 16, max_length: int = 512, local_files_only: bool = False):
        self.name = model_name
        self.model_name = model_name
        self.batch_size = batch_size
        self.max_length = max_length
        self.local_files_only = local_files_only
        self.device = device
        self._pipe = None  # lazy-loaded

    def _load(self):
        if self._pipe is not None:
            return
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
        tok = AutoTokenizer.from_pretrained(self.model_name, local_files_only=self.local_files_only)
        mdl = AutoModelForSequenceClassification.from_pretrained(
            self.model_name, local_files_only=self.local_files_only)
        if self.device is None:
            try:
                import torch
                self.device = 0 if torch.cuda.is_available() else -1
            except Exception:
                self.device = -1
        self._pipe = pipeline("text-classification", model=mdl, tokenizer=tok,
                              top_k=None, device=self.device)

    def predict_proba_batch(self, texts: Sequence[str]) -> List[Tuple[float, float, float]]:
        if not texts:
            return []
        self._load()
        clean = [(t or "").strip() or "." for t in texts]
        out = self._pipe(clean, batch_size=self.batch_size, truncation=True, max_length=self.max_length)
        results = []
        for scores in out:
            m = {d["label"].lower(): float(d["score"]) for d in scores}
            results.append((m.get("positive", 0.0), m.get("neutral", 0.0), m.get("negative", 0.0)))
        return results


class LexiconSentimentModel(SentimentModel):
    """
    Tiny offline fallback (no downloads) for tests / when FinBERT is unavailable.
    NOT a substitute for FinBERT; produces coarse probabilities.
    """
    name = "lexicon-fallback"
    POS = {"beat", "beats", "surge", "surges", "jump", "jumps", "record", "growth", "profit", "gain",
           "gains", "rises", "rise", "upgrade", "upgrades", "strong", "wins", "approval", "dividend", "buyback"}
    NEG = {"miss", "misses", "fall", "falls", "plunge", "plunges", "loss", "losses", "decline", "fraud",
           "probe", "downgrade", "downgrades", "weak", "lawsuit", "penalty", "default", "resigns", "slump"}

    def predict_proba_batch(self, texts):
        out = []
        for t in texts:
            words = re.findall(r"[a-z]+", (t or "").lower())
            p = sum(w in self.POS for w in words)
            n = sum(w in self.NEG for w in words)
            out.append((0.1 + p, 0.8, 0.1 + n))
        return out


# --------------------------------------------------------------------------- #
# Article level
# --------------------------------------------------------------------------- #
def score_articles(articles: Sequence[Article], model: SentimentModel) -> List[Article]:
    """Attach a SentimentResult to each article (in place) and return them."""
    results = model.analyze([a.text for a in articles])
    for a, r in zip(articles, results):
        a.sentiment = r
    return list(articles)


# --------------------------------------------------------------------------- #
# Event level
# --------------------------------------------------------------------------- #
def _source_key(a: Article) -> str:
    return (a.source or a.url).strip().lower()


def aggregate_event_sentiment(
    articles: Iterable[Article],
    primary_source_multiplier: float = 2.0,
    source_weight_fn: Optional[Callable[[Article], float]] = None,
) -> Optional[Dict[str, float]]:
    """
    Event-level sentiment from already-scored articles.

    1. Group articles by independent source; average probabilities within a source.
    2. Weight each source vote: 1.0 (x primary_source_multiplier if any article from
       that source is a primary source) (x optional source_weight_fn, so later groups
       can plug in their configurable source-quality weights).
    3. Weighted-average probabilities, renormalise, sentiment = P(pos) - P(neg).
    """
    groups: Dict[str, List[Article]] = defaultdict(list)
    for a in articles:
        if a.sentiment is not None:
            groups[_source_key(a)].append(a)
    if not groups:
        return None

    tp = tn = tg = tw = 0.0
    primary = False
    for arts in groups.values():
        n = len(arts)
        p = sum(a.sentiment.positive_probability for a in arts) / n
        u = sum(a.sentiment.neutral_probability for a in arts) / n
        g = sum(a.sentiment.negative_probability for a in arts) / n
        w = 1.0
        if any(a.primary_source for a in arts):
            w *= primary_source_multiplier
            primary = True
        if source_weight_fn:
            w *= max(0.0, source_weight_fn(arts[0]))
        tp, tn, tg, tw = tp + w * p, tn + w * u, tg + w * g, tw + w

    if tw <= 0:
        return None
    r = SentimentResult.from_probs(tp / tw, tn / tw, tg / tw)
    return {
        "positive_probability": r.positive_probability,
        "neutral_probability": r.neutral_probability,
        "negative_probability": r.negative_probability,
        "sentiment_score": r.sentiment_score,
        "independent_source_count": len(groups),
        "primary_source_confirmed": primary,
    }
