from events.event_clusterer import ClusteringConfig, EventClusterer, build_enriched_events
from events.event_model import Article, EventType
from models.event_classifier import KeywordRuleClassifier
from models.sentiment import LexiconSentimentModel


def art(i, title, ts, ticker="RELIANCE", source=None, desc="", primary=False):
    return Article.from_raw({"ticker": ticker, "company_name": ticker, "title": title, "description": desc,
                             "url": f"http://x/{ticker}/{i}", "source": source or f"src{i}",
                             "source_type": "NEWS_RSS", "primary_source": primary, "published_at": ts})


Q2 = [
    art(1, "Reliance Q2 net profit rises 12% to Rs 18,000 crore", "2025-10-20T10:00:00Z"),
    art(2, "Reliance Industries Q2 profit up 12%, beats estimates", "2025-10-20T11:00:00Z"),
    art(3, "Reliance posts Rs 18,000 crore net profit in Q2 results", "2025-10-20T13:00:00Z"),
]
OTHER = art(4, "Reliance Jio announces new tariff plans for subscribers", "2025-10-20T12:00:00Z")


def test_same_development_becomes_one_event():
    events, maps = EventClusterer().cluster(Q2)
    assert len(events) == 1 and events[0].article_count == 3
    assert {m.event_id for m in maps} == {events[0].event_id}


def test_different_developments_split():
    events, _ = EventClusterer().cluster(Q2 + [OTHER])
    assert len(events) == 2


def test_different_tickers_never_merge():
    twin = art(9, Q2[0].title, "2025-10-20T10:30:00Z", ticker="TCS")
    events, _ = EventClusterer().cluster([Q2[0], twin])
    assert len(events) == 2


def test_time_window_respected():
    late = art(7, Q2[0].title, "2025-11-20T10:00:00Z")
    events, _ = EventClusterer().cluster([Q2[0], late])
    assert len(events) == 2


def test_article_to_event_mapping_complete_and_unique():
    arts = Q2 + [OTHER]
    events, maps = EventClusterer().cluster(arts)
    assert sorted(m.article_id for m in maps) == sorted(a.article_id for a in arts)
    ids = {e.event_id for e in events}
    assert all(m.event_id in ids for m in maps)


def test_deterministic_and_order_independent_ids():
    e1, _ = EventClusterer().cluster(Q2 + [OTHER])
    e2, _ = EventClusterer().cluster(list(reversed(Q2 + [OTHER])))
    assert {e.event_id for e in e1} == {e.event_id for e in e2}


def test_duplicate_article_ids_ignored():
    events, maps = EventClusterer().cluster(Q2 + [Q2[0]])
    assert events[0].article_count == 3 and len(maps) == 3


def test_empty_input():
    assert EventClusterer().cluster([]) == ([], [])


def test_threshold_configurable():
    strict = EventClusterer(ClusteringConfig(similarity_threshold=0.99))
    events, _ = strict.cluster(Q2)
    assert len(events) == 3


def test_event_metadata_sources_and_primary():
    arts = [art(1, "Reliance Q2 net profit rises 12%", "2025-10-20T10:00:00Z", source="BSE", primary=True),
            art(2, "Reliance Q2 net profit rises 12% crore", "2025-10-20T10:30:00Z", source="Mint"),
            art(3, "Reliance Q2 net profit rises 12% says report", "2025-10-20T11:00:00Z", source="Mint")]
    (ev,), _ = EventClusterer().cluster(arts)
    assert ev.independent_source_count == 2 and ev.primary_source_confirmed


def test_end_to_end_enrichment():
    _, events, _ = build_enriched_events(Q2 + [OTHER], LexiconSentimentModel(), KeywordRuleClassifier())
    earn = next(e for e in events if e.article_count == 3)
    assert earn.event_type == EventType.EARNINGS
    assert earn.sentiment_score is not None and -1 <= earn.sentiment_score <= 1
    assert abs(earn.positive_probability + earn.neutral_probability + earn.negative_probability - 1) < 1e-9
