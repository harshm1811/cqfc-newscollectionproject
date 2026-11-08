"""Run: python -m pytest tests/  (FinBERT test is skipped unless transformers is installed)."""
import math
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
    assert SentimentResult.from_probs(0, 0, 0).sentiment_score == 0


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
    assert agg["independent_source_count"] == 2
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
    except ImportError:
        return  # skipped
    from models.sentiment import FinBERTSentimentModel
    r = FinBERTSentimentModel().analyze(["Company reports record quarterly profit, beating estimates"])[0]
    assert r.sentiment_score > 0
