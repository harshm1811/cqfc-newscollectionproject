"""
models/sentiment.py - Financial sentiment (FinBERT) + event-level aggregation.

* Article level: P(pos), P(neu), P(neg), sentiment_score = P(pos) - P(neg).
* Event level: NOT a plain mean of articles. Repeated articles from the same
  publisher would dominate, so each publisher group gets one vote
  (articles within a source are averaged first), and primary-source articles
  can be given extra weight. Probabilities are averaged and re-normalised,
  then score = P(pos) - P(neg) is recomputed from the aggregate probabilities.

The model is replaceable: implement `SentimentModel.predict_proba_batch`.
"""

from __future__ import annotations

import logging
import math
import os
import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass
from typing import Callable, Dict, Iterable, List, Optional, Sequence, Tuple

from events.event_model import Article, SentimentResult

logger = logging.getLogger("models.sentiment")


class SentimentModel(ABC):
    name: str = "base"

    @abstractmethod
    def predict_proba_batch(self, texts: Sequence[str]) -> List[Tuple[float, float, float]]:
        """Return (P_pos, P_neu, P_neg) for each text."""

    def analyze(self, texts: Sequence[str]) -> List[SentimentResult]:
        values = self.predict_proba_batch(list(texts))
        if len(values) != len(texts):
            raise RuntimeError(f"{self.name} returned {len(values)} probability rows for {len(texts)} texts")
        return [SentimentResult.from_probs(p, n, g, self.name) for p, n, g in values]


@dataclass
class SentimentConfig:
    """Model selection and explicit lexicon-fallback policy."""
    model_name: str = "ProsusAI/finbert"
    fallback_enabled: bool = False
    local_files_only: bool = False
    batch_size: int = 16
    max_length: int = 512
    device: Optional[int] = None
    model: str = "finbert"

    def __post_init__(self):
        self.model = self.model.strip().casefold()
        if self.model not in {"finbert", "lexicon"}:
            raise ValueError("sentiment model must be 'finbert' or 'lexicon'")
        if self.batch_size < 1 or self.max_length < 1:
            raise ValueError("batch_size and max_length must be positive")

    @classmethod
    def from_env(cls):
        """Read optional SENTIMENT_* settings without requiring dotenv."""
        fallback = os.getenv("SENTIMENT_FALLBACK_ENABLED", "false").strip().casefold()
        if fallback not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("SENTIMENT_FALLBACK_ENABLED must be true or false")
        local_only = os.getenv("SENTIMENT_LOCAL_FILES_ONLY", "false").strip().casefold()
        if local_only not in {"true", "false", "1", "0", "yes", "no"}:
            raise ValueError("SENTIMENT_LOCAL_FILES_ONLY must be true or false")
        device_text = os.getenv("SENTIMENT_DEVICE")
        try:
            if device_text is None:
                device = None
            elif device_text.strip().casefold() == "cpu":
                device = -1
            elif device_text.strip().casefold() == "cuda":
                device = 0
            else:
                device = int(device_text)
        except ValueError as exc:
            raise ValueError("SENTIMENT_DEVICE must be 'cpu', 'cuda', or an integer (use -1 for CPU)") from exc
        return cls(
            model=os.getenv("SENTIMENT_MODEL", "finbert"),
            model_name=os.getenv("SENTIMENT_MODEL_NAME", "ProsusAI/finbert"),
            fallback_enabled=fallback in {"true", "1", "yes"},
            local_files_only=local_only in {"true", "1", "yes"},
            device=device,
        )


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
        # Streamlit may run as a hidden Windows process without a valid console
        # handle. Hugging Face's tqdm weight-loading progress can then raise
        # OSError(22) before the model is ready, so disable terminal progress.
        os.environ.setdefault("TQDM_DISABLE", "1")
        os.environ.setdefault("HF_HUB_DISABLE_PROGRESS_BARS", "1")
        from transformers import AutoModelForSequenceClassification, AutoTokenizer, pipeline
        from transformers.utils import logging as transformers_logging
        transformers_logging.disable_progress_bar()
        try:
            from huggingface_hub.utils import disable_progress_bars
            disable_progress_bars()
        except ImportError:
            pass
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

    def ensure_loaded(self):
        """Initialize dependencies, tokenizer and model before inference begins."""
        self._load()

    def predict_proba_batch(self, texts: Sequence[str]) -> List[Tuple[float, float, float]]:
        if not texts:
            return []
        self._load()
        clean = [(t or "").strip() or "." for t in texts]
        out = self._pipe(clean, batch_size=self.batch_size, truncation=True, max_length=self.max_length)
        if len(out) != len(clean):
            raise RuntimeError(f"FinBERT returned {len(out)} rows for {len(clean)} input texts")
        results = []
        for scores in out:
            if isinstance(scores, dict):
                scores = [scores]
            m = {str(d["label"]).strip().casefold(): float(d["score"]) for d in scores}
            required = {"positive", "neutral", "negative"}
            if set(m) != required:
                raise RuntimeError(f"FinBERT output labels must be {sorted(required)}; received {sorted(m)}")
            values = (m["positive"], m["neutral"], m["negative"])
            if any(not math.isfinite(value) or value < 0 for value in values):
                raise RuntimeError("FinBERT returned invalid probabilities")
            total = sum(values)
            if total <= 0:
                raise RuntimeError("FinBERT returned probabilities with zero total")
            results.append(tuple(value / total for value in values))
        return results


def resolve_sentiment_model(config: Optional[SentimentConfig] = None):
    """Select and initialize the configured primary model before inference."""
    config = config or SentimentConfig.from_env()
    if config.model == "lexicon":
        model = LexiconSentimentModel(name="lexicon")
        logger.warning("Using lexicon model selected by SENTIMENT_MODEL=lexicon")
        return model, None
    try:
        model = FinBERTSentimentModel(
            model_name=config.model_name,
            device=config.device,
            batch_size=config.batch_size,
            max_length=config.max_length,
            local_files_only=config.local_files_only,
        )
        model.ensure_loaded()
    except Exception as exc:
        reason = f"FinBERT initialization failed ({type(exc).__name__}): {exc}"
        if not config.fallback_enabled:
            raise RuntimeError(reason + "; lexicon fallback is disabled") from exc
        model = LexiconSentimentModel()
        logger.warning("Using %s because %s", model.name, reason)
        return model, reason
    logger.warning("Using FinBERT model %s", model.model_name)
    return model, None


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

    def __init__(self, *, name: str = "lexicon-fallback"):
        self.name = name

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
    # Publisher grouping limits repeated publisher influence; it does not
    # establish source independence or common origin.
    return (a.source or a.url).strip().casefold()


def aggregate_event_sentiment(
    articles: Iterable[Article],
    primary_source_multiplier: float = 2.0,
    source_weight_fn: Optional[Callable[[Article], float]] = None,
) -> Optional[Dict[str, float]]:
    """
    Event-level sentiment from already-scored articles.

    1. Group articles by publisher; average probabilities within a publisher.
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
        "independent_source_count": len({
            str(getattr(a, "independent_source_id", None) or a.source or a.article_id).casefold()
            for arts in groups.values() for a in arts if a.independent_source is True
        }),
        "primary_source_confirmed": primary,
    }
