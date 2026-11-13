import math

import pytest

from events.event_model import Article, Event, EventType
from models import event_classifier
from models.event_classifier import EventClassifier, FinDeBERTaEventClassifier, Classification


LABELS = [
    "CSR/Brand", "Deal", "Dividend", "Employment", "Expense", "Facility",
    "FinancialReport", "Financing", "Investment", "Legal", "Macroeconomics",
    "Merger/Acquisition", "Product/Service", "Profit/Loss", "Rating", "Revenue",
    "SalesVolume", "SecurityValue",
]


def fake_model(monkeypatch, logits, thresholds):
    torch = pytest.importorskip("torch")

    class Tokenizer:
        def __call__(self, *_args, **kwargs):
            assert kwargs["truncation"] is True and kwargs["max_length"] == 128
            return {"input_ids": torch.tensor([[1]])}

    class Model:
        config = type("Config", (), {"id2label": dict(enumerate(LABELS))})()

        def __call__(self, **_kwargs):
            return type("Output", (), {"logits": torch.tensor([logits], dtype=torch.float32)})()

    monkeypatch.setattr(event_classifier, "_load_model", lambda *_args: (Tokenizer(), Model(), torch.device("cpu"), thresholds))


def test_canonical_labels_are_exactly_supported_model_labels():
    assert [label for label in event_classifier.EVENT_LABELS] == LABELS
    assert EventType.OTHER.value == "OTHER"


def test_multilabel_sigmoid_thresholds_and_order(monkeypatch):
    logits = [-5.0] * len(LABELS)
    thresholds = [0.99] * len(LABELS)
    logits[1], logits[2] = 2.0, 1.0
    thresholds[1], thresholds[2] = 0.8, 0.7
    fake_model(monkeypatch, logits, thresholds)

    result = FinDeBERTaEventClassifier().classify_text("Financial headline")

    assert result.event_type is EventType.DEAL
    assert result.labels == ["Deal", "Dividend"]
    assert result.scores["Deal"] == pytest.approx(1 / (1 + math.exp(-2)))
    assert result.scores["Dividend"] == pytest.approx(1 / (1 + math.exp(-1)))


def test_other_has_no_fabricated_model_probability(monkeypatch):
    fake_model(monkeypatch, [-4.0] * len(LABELS), [0.6] * len(LABELS))
    result = FinDeBERTaEventClassifier().classify_text("Unrelated text")
    assert result.event_type is EventType.OTHER
    assert result.confidence == 0.0
    assert result.scores == {}
    assert result.labels == ["OTHER"]


def test_event_record_keeps_labels_and_event_confidence():
    event = Event("e1", "ABC", "Headline", event_type=EventType.DEAL,
                  type_confidence=0.91, type_scores={"Deal": 0.91}, event_labels=["Deal", "Revenue"])
    row = event.to_group4_record()
    assert row["event_type"] == "Deal"
    assert row["event_labels"] == ["Deal", "Revenue"]
    assert row["event_type_confidence"] == 0.91


def test_classifier_interface_accepts_custom_classifier():
    class FixedClassifier(EventClassifier):
        def classify_text(self, text):
            return Classification(EventType.DEAL, 0.9, {"Deal": 0.9}, labels=["Deal"])

    article = Article.from_raw({"article_id": "a1", "ticker": "ABC", "title": "A deal"})
    event = Event("e1", "ABC", "A deal")
    FixedClassifier().classify_event(event, [article])
    assert event.event_type is EventType.DEAL
    assert event.event_labels == ["Deal"]
