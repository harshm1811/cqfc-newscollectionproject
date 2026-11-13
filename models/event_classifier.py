"""Pretrained FinDeBERTa multi-label event classification."""
from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from functools import lru_cache
from typing import Dict, List, Sequence

from events.event_model import Article, Event, EventType

MODEL_NAME = "ritessshhh/FinDeBERTa"
EVENT_LABELS = tuple(item.value for item in EventType if item is not EventType.OTHER)


@dataclass
class Classification:
    event_type: EventType
    confidence: float
    scores: Dict[str, float] = field(default_factory=dict)
    matched: List[str] = field(default_factory=list)
    labels: List[str] = field(default_factory=list)


class EventClassifier(ABC):
    @abstractmethod
    def classify_text(self, text: str) -> Classification: ...

    def classify_articles(self, articles: Sequence[Article]) -> Classification:
        predictions = [self.classify_text(article.text) for article in articles]
        scores: Dict[str, float] = {}
        for result in predictions:
            result_scores = result.scores
            if not result_scores and result.event_type is not EventType.OTHER and result.confidence > 0:
                result_scores = {result.event_type.value: result.confidence}
            for label, score in result_scores.items():
                scores[label] = max(scores.get(label, 0.0), score)
        labels = sorted(scores, key=scores.get, reverse=True)
        if not labels:
            return Classification(EventType.OTHER, 0.0, {}, [], [EventType.OTHER.value])
        primary = labels[0]
        return Classification(EventType(primary), scores[primary], scores, labels, labels)

    def classify_event(self, event: Event, articles: Sequence[Article]) -> Event:
        result = self.classify_articles(articles)
        event.event_type = result.event_type
        event.type_confidence = result.confidence
        event.type_scores = result.scores
        event.event_labels = result.labels
        return event


@lru_cache(maxsize=1)
def _load_model(model_name: str, device_name: str | None, local_files_only: bool):
    import numpy as np
    import torch
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import EntryNotFoundError, LocalEntryNotFoundError
    from transformers import AutoModelForSequenceClassification, AutoTokenizer

    tokenizer = AutoTokenizer.from_pretrained(model_name, local_files_only=local_files_only)
    model = AutoModelForSequenceClassification.from_pretrained(model_name, local_files_only=local_files_only)
    model_labels = {str(model.config.id2label[index]) for index in range(model.config.num_labels)}
    if model_labels != set(EVENT_LABELS):
        raise RuntimeError(f"Unexpected FinDeBERTa labels: {sorted(model_labels)}")
    device = torch.device(device_name or ("cuda" if torch.cuda.is_available() else "cpu"))
    model.to(device)
    model.eval()
    try:
        path = hf_hub_download(model_name, "thresholds.npy", local_files_only=local_files_only)
        thresholds = np.load(path)
        if len(thresholds) != model.config.num_labels:
            raise ValueError("FinDeBERTa thresholds length does not match model labels")
    except (EntryNotFoundError, LocalEntryNotFoundError):
        thresholds = None
    return tokenizer, model, device, thresholds


class FinDeBERTaEventClassifier(EventClassifier):
    """Cached model loading and inference with original label probabilities."""
    def __init__(self, model_name: str = MODEL_NAME, *, device: str | None = None,
                 local_files_only: bool = False, max_length: int = 128):
        self.model_name = model_name
        self.device_name = device
        self.local_files_only = local_files_only
        self.max_length = max_length

    def classify_text(self, text: str) -> Classification:
        import torch

        tokenizer, model, device, thresholds = _load_model(self.model_name, self.device_name, self.local_files_only)
        encoded = tokenizer(text or "", return_tensors="pt", truncation=True, max_length=self.max_length)
        encoded = {key: value.to(device) for key, value in encoded.items()}
        with torch.inference_mode():
            probabilities = torch.sigmoid(model(**encoded).logits)[0].cpu().tolist()
        labels_by_id = model.config.id2label
        selected = []
        for index, probability in enumerate(probabilities):
            label = str(labels_by_id[index])
            threshold = float(thresholds[index]) if thresholds is not None else 0.5
            if probability >= threshold:
                selected.append((label, float(probability)))
        selected.sort(key=lambda pair: pair[1], reverse=True)
        if not selected:
            return Classification(EventType.OTHER, 0.0, {}, [], [EventType.OTHER.value])
        scores = dict(selected)
        primary = selected[0][0]
        return Classification(EventType(primary), scores[primary], scores, list(scores), list(scores))


# Compatibility name retained for existing injection points; it is now FinDeBERTa.
KeywordRuleClassifier = FinDeBERTaEventClassifier


class CompositeEventClassifier(EventClassifier):
    def __init__(self, classifiers: Sequence[EventClassifier], threshold: float = 0.5):
        self.classifiers = list(classifiers)
        self.threshold = threshold

    def classify_text(self, text: str) -> Classification:
        best = None
        for classifier in self.classifiers:
            result = classifier.classify_text(text)
            if result.event_type is not EventType.OTHER and result.confidence >= self.threshold:
                return result
            if best is None or result.confidence > best.confidence:
                best = result
        return best or Classification(EventType.OTHER, 0.0, {}, [], [EventType.OTHER.value])
