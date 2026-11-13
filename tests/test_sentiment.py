"""Run: python -m pytest tests/  (FinBERT test is skipped unless transformers is installed)."""
import math
import pytest
from events.event_model import Article, SentimentResult
from models.sentiment import (LexiconSentimentModel, SentimentModel, aggregate_event_sentiment,
                              score_articles)


def art(url, source, title, primary=False):
    return Article.from_raw({"ticker": "RELIANCE", "company_name": "Reliance", "title": title,
                             "url": url, "source": source, "source_type": "NEWS_RSS",
                             "primary_source": primary, "published_at": "2025-01-01T10:00:00Z"})


class Fixed(SentimentModel):
    name = "fixed"
    def __init__(self, table): self.table = table
    def predict_proba_batch(self, texts): return [self.table[t] for t in texts]


def test_score_is_pos_minus_neg_and_probs_kept():
    r = SentimentResult.from_probs(0.7, 0.2, 0.1)
    assert math.isclose(r.sentiment_score, 0.6)
    assert math.isclose(r.positive_probability + r.neutral_probability + r.negative_probability, 1.0)


def test_probabilities_are_renormalised():
    r = SentimentResult.from_probs(2, 1, 1)
    assert math.isclose(r.positive_probability, 0.5) and math.isclose(r.sentiment_score, 0.25)


def test_score_range():
    assert SentimentResult.from_probs(1, 0, 0).sentiment_score == 1
    assert SentimentResult.from_probs(0, 0, 1).sentiment_score == -1
    import pytest
    with pytest.raises(ValueError, match="at least one"):
        SentimentResult.from_probs(0, 0, 0)


def test_lexicon_direction():
    m = LexiconSentimentModel()
    pos, neg = m.analyze(["Profit surges to record", "Fraud probe, shares plunge"])
    assert pos.sentiment_score > 0 > neg.sentiment_score


def test_score_articles_attaches_sentiment():
    a = [art("u1", "s1", "Profit surges")]
    score_articles(a, LexiconSentimentModel())
    assert a[0].sentiment is not None


def test_event_sentiment_not_simple_mean_syndicated_copies_dont_dominate():
    # 4 copies from one source (positive) vs 1 article from another source (negative)
    arts = [art(f"u{i}", "wire", f"pos{i}") for i in range(4)] + [art("u9", "other", "neg")]
    model = Fixed({**{f"pos{i}": (0.9, 0.1, 0.0) for i in range(4)}, "neg": (0.0, 0.1, 0.9)})
    score_articles(arts, model)
    agg = aggregate_event_sentiment(arts)
    naive = sum(a.sentiment.sentiment_score for a in arts) / len(arts)
    assert agg["independent_source_count"] == 0  # publisher groups are not proof of independent origins
    assert math.isclose(agg["sentiment_score"], 0.0, abs_tol=1e-9)  # one vote each
    assert naive > 0.4                                              # naive mean would be biased


def test_primary_source_gets_extra_weight_and_flag():
    arts = [art("u1", "bse", "p", primary=True), art("u2", "blog", "n")]
    score_articles(arts, Fixed({"p": (0.9, 0.1, 0.0), "n": (0.0, 0.1, 0.9)}))
    agg = aggregate_event_sentiment(arts, primary_source_multiplier=3.0)
    assert agg["primary_source_confirmed"] and agg["sentiment_score"] > 0
    assert math.isclose(agg["positive_probability"] + agg["neutral_probability"] + agg["negative_probability"], 1.0)


def test_custom_source_weight_fn_is_pluggable():
    arts = [art("u1", "a", "p"), art("u2", "b", "n")]
    score_articles(arts, Fixed({"p": (0.9, 0.1, 0.0), "n": (0.0, 0.1, 0.9)}))
    agg = aggregate_event_sentiment(arts, source_weight_fn=lambda a: 0.0 if a.source == "b" else 1.0)
    assert math.isclose(agg["sentiment_score"], 0.9)


def test_empty_returns_none():
    assert aggregate_event_sentiment([]) is None


def test_finbert_real_model_if_available():
    try:
        import transformers  # noqa: F401
        import torch  # noqa: F401
    except (ImportError, OSError):
        pytest.skip("FinBERT inference dependencies are not installed")
    from models.sentiment import FinBERTSentimentModel
    try:
        r = FinBERTSentimentModel(local_files_only=True).analyze(
            ["Company reports record quarterly profit, beating estimates"]
        )[0]
    except OSError as exc:
        pytest.skip(f"ProsusAI/finbert weights are not available in the local cache: {exc}")
    assert 0 <= r.positive_probability <= 1
    assert 0 <= r.neutral_probability <= 1
    assert 0 <= r.negative_probability <= 1
    assert r.positive_probability + r.neutral_probability + r.negative_probability == pytest.approx(1.0)
    assert -1 <= r.sentiment_score <= 1
    assert r.model_name == "ProsusAI/finbert"


def test_finbert_batch_output_is_normalized_and_labels_are_mapped():
    from models.sentiment import FinBERTSentimentModel
    calls = {}
    def fake_pipe(texts, **kwargs):
        calls["texts"] = texts
        calls.update(kwargs)
        return [[
            {"label": "positive", "score": 0.2},
            {"label": "neutral", "score": 0.8},
            {"label": "negative", "score": 0.6},
        ] for _ in texts]
    model = FinBERTSentimentModel()
    model._pipe = fake_pipe
    results = model.analyze(["  up  ", "down"])
    assert model.model_name == "ProsusAI/finbert"
    assert calls["texts"] == ["up", "down"]
    assert calls["batch_size"] == model.batch_size
    assert calls["truncation"] is True and calls["max_length"] == model.max_length
    for result in results:
        assert result.positive_probability == 0.125
        assert result.neutral_probability == 0.5
        assert result.negative_probability == pytest.approx(0.375)
        assert result.sentiment_score == pytest.approx(-0.25)
        assert result.model_name == "ProsusAI/finbert"
        assert 0 <= result.positive_probability <= 1
        assert 0 <= result.neutral_probability <= 1
        assert 0 <= result.negative_probability <= 1
        assert result.positive_probability + result.neutral_probability + result.negative_probability == pytest.approx(1.0)


def test_finbert_rejects_missing_probability_labels():
    import pytest
    from models.sentiment import FinBERTSentimentModel
    model = FinBERTSentimentModel()
    model._pipe = lambda texts, **kwargs: [[{"label": "positive", "score": 1.0}]]
    with pytest.raises(RuntimeError, match="output labels"):
        model.predict_proba_batch(["sample"])




def test_finbert_initializes_prosus_model_tokenizer_and_pipeline(monkeypatch):
    import sys
    import types
    from models.sentiment import FinBERTSentimentModel
    calls = []
    tokenizer = object()
    model_weights = object()
    class Loader:
        @classmethod
        def from_pretrained(cls, name, **kwargs):
            calls.append((cls.__name__, name, kwargs))
            return tokenizer if cls.__name__ == "AutoTokenizer" else model_weights
    class AutoTokenizer(Loader): pass
    class AutoModelForSequenceClassification(Loader): pass
    def fake_pipeline(task, **kwargs):
        calls.append(("pipeline", task, kwargs))
        return lambda texts, **kw: [[{"label": "positive", "score": .2}, {"label": "neutral", "score": .3}, {"label": "negative", "score": .5}] for _ in texts]
    fake = types.ModuleType("transformers")
    fake.AutoTokenizer = AutoTokenizer
    fake.AutoModelForSequenceClassification = AutoModelForSequenceClassification
    fake.pipeline = fake_pipeline
    monkeypatch.setitem(sys.modules, "transformers", fake)
    sentiment = FinBERTSentimentModel(device=-1)
    sentiment.ensure_loaded()
    assert calls[0][1] == calls[1][1] == "ProsusAI/finbert"
    assert calls[0][0] == "AutoTokenizer"
    assert calls[1][0] == "AutoModelForSequenceClassification"
    assert calls[2][2]["tokenizer"] is tokenizer
    assert calls[2][2]["model"] is model_weights
    assert calls[2][2]["device"] == -1


def test_model_selection_falls_back_only_during_initialization(monkeypatch):
    import pytest
    from models.sentiment import FinBERTSentimentModel, LexiconSentimentModel, SentimentConfig, resolve_sentiment_model
    def fail_load(self):
        raise OSError("weights unavailable")
    monkeypatch.setattr(FinBERTSentimentModel, "ensure_loaded", fail_load)
    model, reason = resolve_sentiment_model(SentimentConfig(fallback_enabled=True))
    assert isinstance(model, LexiconSentimentModel)
    assert model.name == "lexicon-fallback"
    assert "weights unavailable" in reason
    with pytest.raises(RuntimeError, match="fallback is disabled"):
        resolve_sentiment_model(SentimentConfig(fallback_enabled=False))


def test_sentiment_configuration_reads_environment_and_selects_lexicon(monkeypatch):
    from models.sentiment import SentimentConfig, resolve_sentiment_model
    monkeypatch.setenv("SENTIMENT_MODEL", "lexicon")
    monkeypatch.setenv("SENTIMENT_FALLBACK_ENABLED", "false")
    monkeypatch.setenv("SENTIMENT_LOCAL_FILES_ONLY", "true")
    monkeypatch.setenv("SENTIMENT_DEVICE", "cpu")
    config = SentimentConfig.from_env()
    assert config.model == "lexicon"
    assert config.fallback_enabled is False
    assert config.local_files_only is True
    assert config.device == -1
    model, reason = resolve_sentiment_model()
    assert isinstance(model, LexiconSentimentModel)
    assert reason is None


def test_pipeline_uses_environment_model_selection(monkeypatch):
    from group3_pipeline import run_group3_pipeline
    monkeypatch.setenv("SENTIMENT_MODEL", "lexicon")
    result = run_group3_pipeline([{"article_id": "a", "ticker": "ABC", "title": "Profit rises"}])
    assert result.sentiment_model_name == "lexicon"
    assert result.sentiment_fallback_reason is None


def test_sentiment_configuration_defaults_to_finbert(monkeypatch):
    from models.sentiment import SentimentConfig
    for key in ("SENTIMENT_MODEL", "SENTIMENT_MODEL_NAME", "SENTIMENT_FALLBACK_ENABLED",
                "SENTIMENT_LOCAL_FILES_ONLY", "SENTIMENT_DEVICE"):
        monkeypatch.delenv(key, raising=False)
    config = SentimentConfig.from_env()
    assert config.model == "finbert"
    assert config.model_name == "ProsusAI/finbert"
    assert config.fallback_enabled is False


def test_sentiment_inference_failure_does_not_switch_models():
    import pytest
    class BrokenModel(SentimentModel):
        name = "test-model"
        def predict_proba_batch(self, texts):
            raise OSError("inference broke")
    from group3_pipeline import run_group3_pipeline
    with pytest.raises(RuntimeError, match="no model switch was attempted"):
        run_group3_pipeline([{"article_id": "a", "ticker": "ABC", "title": "Headline"}], sentiment_model=BrokenModel())


def test_pipeline_records_fallback_model_and_reason(monkeypatch):
    import group3_pipeline as pipeline
    model = LexiconSentimentModel()
    monkeypatch.setattr(pipeline, "resolve_sentiment_model", lambda config: (model, "mock initialization failure"))
    result = pipeline.run_group3_pipeline([{"article_id": "a", "ticker": "ABC", "title": "Headline"}])
    assert result.sentiment_model_name == "lexicon-fallback"
    assert result.sentiment_fallback_reason == "mock initialization failure"


def test_explicit_finbert_initialization_failure_obeys_fallback_setting(monkeypatch):
    import pytest
    from models.sentiment import FinBERTSentimentModel, LexiconSentimentModel, SentimentConfig
    from group3_pipeline import run_group3_pipeline
    monkeypatch.setattr(FinBERTSentimentModel, "ensure_loaded", lambda self: (_ for _ in ()).throw(OSError("cache miss")))
    article = [{"article_id": "a", "ticker": "ABC", "title": "Headline"}]
    result = run_group3_pipeline(article, sentiment_model=FinBERTSentimentModel(),
                                 sentiment_config=SentimentConfig(fallback_enabled=True))
    assert result.sentiment_model_name == LexiconSentimentModel.name
    assert "cache miss" in result.sentiment_fallback_reason
    with pytest.raises(RuntimeError, match="fallback is disabled"):
        run_group3_pipeline(article, sentiment_model=FinBERTSentimentModel(),
                            sentiment_config=SentimentConfig(fallback_enabled=False))


def test_finbert_inference_failure_rescores_entire_batch_with_explicit_fallback(monkeypatch):
    from models.sentiment import FinBERTSentimentModel, LexiconSentimentModel
    from group3_pipeline import run_group3_pipeline
    monkeypatch.setattr(FinBERTSentimentModel, "ensure_loaded", lambda self: None)
    monkeypatch.setattr(FinBERTSentimentModel, "analyze", lambda self, texts: (_ for _ in ()).throw(OSError("inference unavailable")))
    records = [
        {"article_id": "a1", "ticker": "ABC", "title": "Profit surges"},
        {"article_id": "a2", "ticker": "ABC", "title": "Shares fall"},
    ]
    from models.sentiment import SentimentConfig
    result = run_group3_pipeline(records, sentiment_config=SentimentConfig(fallback_enabled=True))
    assert result.sentiment_model_name == LexiconSentimentModel.name
    assert "FinBERT inference failed" in result.sentiment_fallback_reason
    assert all(article.sentiment.model_name == "lexicon-fallback" for article in result.articles)


def test_finbert_inference_failure_is_raised_when_fallback_disabled(monkeypatch):
    from models.sentiment import FinBERTSentimentModel, SentimentConfig
    from group3_pipeline import run_group3_pipeline
    monkeypatch.setattr(FinBERTSentimentModel, "ensure_loaded", lambda self: None)
    monkeypatch.setattr(FinBERTSentimentModel, "analyze", lambda self, texts: (_ for _ in ()).throw(OSError("inference unavailable")))
    with pytest.raises(RuntimeError, match="fallback is disabled"):
        run_group3_pipeline(
            [{"article_id": "a", "ticker": "ABC", "title": "Headline"}],
            sentiment_model=FinBERTSentimentModel(),
            sentiment_config=SentimentConfig(fallback_enabled=False),
        )
