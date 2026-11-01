"""
events/event_clusterer.py - Group articles describing the same development into one Event.

Method (V1, dependency-free): TF-IDF cosine similarity over title+description,
constrained by ticker and a time window, with single-link greedy assignment:

    for each article (chronological):
        compare to articles already in each open event of the same ticker
        (within `time_window_hours` of that event);
        join the best event if max similarity >= `similarity_threshold`,
        otherwise start a new event.

Replaceable: pass any `TextVectorizer` (e.g. a sentence-embedding model) that
returns L2-normalised sparse/dense vectors via the same interface.

Event ids are deterministic: EVT-<sha1(ticker|earliest article id)[:10]>.
Maintains ARTICLE -> EVENT mapping (ArticleEventMapping).
"""

from __future__ import annotations

import hashlib
import math
import re
from abc import ABC, abstractmethod
from collections import Counter, defaultdict
from dataclasses import dataclass
from datetime import timedelta
from typing import Dict, List, Sequence, Tuple

from events.event_model import Article, ArticleEventMapping, Event

_STOPWORDS = set("""a an the and or of to in on for at by with from as is are was were be been it its this that these
those has have had will would may might can could said says say after before over into amid new news report reports
reported india indian ltd limited inc corp company shares share stock stocks market markets today""".split())


def tokenize(text: str) -> List[str]:
    toks = re.findall(r"[a-z0-9][a-z0-9.%&'-]*", (text or "").lower())
    return [t.strip(".'-") for t in toks if t.strip(".'-") and t.strip(".'-") not in _STOPWORDS and len(t) > 1]


SparseVec = Dict[str, float]


class TextVectorizer(ABC):
    @abstractmethod
    def fit_transform(self, texts: Sequence[str]) -> List[SparseVec]:
        """Return one L2-normalised sparse vector per text."""


class TfidfVectorizer(TextVectorizer):
    """TF-IDF (smoothed IDF), fit on the batch being clustered. Unigrams by default:
    bigrams hurt recall on short, paraphrased headlines."""

    def __init__(self, use_bigrams: bool = False):
        self.use_bigrams = use_bigrams

    def _features(self, text: str) -> List[str]:
        toks = tokenize(text)
        feats = list(toks)
        if self.use_bigrams:
            feats += [f"{a}_{b}" for a, b in zip(toks, toks[1:])]
        return feats

    def fit_transform(self, texts: Sequence[str]) -> List[SparseVec]:
        docs = [Counter(self._features(t)) for t in texts]
        n = len(docs)
        df: Counter = Counter()
        for d in docs:
            df.update(d.keys())
        vecs: List[SparseVec] = []
        for d in docs:
            v = {t: (1 + math.log(c)) * (math.log((1 + n) / (1 + df[t])) + 1) for t, c in d.items()}
            norm = math.sqrt(sum(x * x for x in v.values())) or 1.0
            vecs.append({t: x / norm for t, x in v.items()})
        return vecs


def cosine(a: SparseVec, b: SparseVec) -> float:
    if len(a) > len(b):
        a, b = b, a
    return sum(x * b.get(t, 0.0) for t, x in a.items())


@dataclass
class ClusteringConfig:
    similarity_threshold: float = 0.25     # tune on real data
    time_window_hours: float = 72.0        # article must be within this of the event's articles
    max_cluster_age_hours: float = 168.0   # event cannot stretch beyond a week


class EventClusterer:
    def __init__(self, config: ClusteringConfig = None, vectorizer: TextVectorizer = None):
        self.config = config or ClusteringConfig()
        self.vectorizer = vectorizer or TfidfVectorizer()

    @staticmethod
    def _clean_text(a: Article) -> str:
        """Drop the company/ticker words: every article for a ticker has them, so they carry no signal."""
        drop = set(tokenize(f"{a.company_name} {a.ticker}")) | {"industries", "industry", "group"}
        return " ".join(t for t in tokenize(a.text) if t not in drop)

    @staticmethod
    def _event_id(ticker: str, first_article_id: str) -> str:
        return "EVT-" + hashlib.sha1(f"{ticker}|{first_article_id}".encode()).hexdigest()[:10]

    def cluster(self, articles: Sequence[Article]) -> Tuple[List[Event], List[ArticleEventMapping]]:
        cfg = self.config
        # de-duplicate by article_id, then chronological order (stable)
        uniq: Dict[str, Article] = {}
        for a in articles:
            uniq.setdefault(a.article_id, a)
        ordered = sorted(uniq.values(), key=lambda a: (a.timestamp, a.article_id))
        if not ordered:
            return [], []

        vecs = dict(zip([a.article_id for a in ordered],
                        self.vectorizer.fit_transform([self._clean_text(a) for a in ordered])))

        window = timedelta(hours=cfg.time_window_hours)
        max_age = timedelta(hours=cfg.max_cluster_age_hours)

        members: Dict[str, List[Article]] = {}               # event_id -> articles
        by_ticker: Dict[str, List[str]] = defaultdict(list)  # ticker -> event_ids
        mappings: List[ArticleEventMapping] = []

        for art in ordered:
            best_eid, best_sim = None, 0.0
            for eid in by_ticker[art.ticker]:
                arts = members[eid]
                if art.timestamp - arts[0].timestamp > max_age:
                    continue
                if art.timestamp - arts[-1].timestamp > window:
                    continue
                sim = max(cosine(vecs[art.article_id], vecs[m.article_id]) for m in arts)
                if sim > best_sim:
                    best_eid, best_sim = eid, sim
            if best_eid is not None and best_sim >= cfg.similarity_threshold:
                members[best_eid].append(art)
                mappings.append(ArticleEventMapping(art.article_id, best_eid, round(best_sim, 4)))
            else:
                eid = self._event_id(art.ticker, art.article_id)
                members[eid] = [art]
                by_ticker[art.ticker].append(eid)
                mappings.append(ArticleEventMapping(art.article_id, eid, 1.0))

        events = [self._build_event(eid, arts, vecs) for eid, arts in members.items()]
        return events, mappings

    @staticmethod
    def _build_event(eid: str, arts: List[Article], vecs: Dict[str, SparseVec]) -> Event:
        # representative headline = article closest to the cluster centroid
        centroid: SparseVec = defaultdict(float)
        for a in arts:
            for t, x in vecs[a.article_id].items():
                centroid[t] += x
        rep = max(arts, key=lambda a: cosine(vecs[a.article_id], centroid)) if len(arts) > 1 else arts[0]
        return Event(
            event_id=eid,
            ticker=arts[0].ticker,
            title=rep.title,
            article_ids=[a.article_id for a in arts],
            first_article_at=arts[0].timestamp,
            last_article_at=arts[-1].timestamp,
            article_count=len(arts),
            independent_source_count=len({(a.source or a.url).lower() for a in arts}),
            primary_source_confirmed=any(a.primary_source for a in arts),
        )


def build_enriched_events(articles, sentiment_model, classifier, clusterer=None, **agg_kwargs):
    """
    Convenience orchestration for Person 1's whole stage:
      score articles -> cluster -> classify events -> event-level sentiment.
    Returns (articles, events, mappings).
    """
    from models.sentiment import score_articles, aggregate_event_sentiment

    clusterer = clusterer or EventClusterer()
    articles = score_articles(list(articles), sentiment_model)
    events, mappings = clusterer.cluster(articles)
    by_id = {a.article_id: a for a in articles}
    for ev in events:
        arts = [by_id[i] for i in ev.article_ids]
        classifier.classify_event(ev, arts)
        agg = aggregate_event_sentiment(arts, **agg_kwargs)
        if agg:
            ev.positive_probability = agg["positive_probability"]
            ev.neutral_probability = agg["neutral_probability"]
            ev.negative_probability = agg["negative_probability"]
            ev.sentiment_score = agg["sentiment_score"]
            ev.independent_source_count = int(agg["independent_source_count"])
            ev.primary_source_confirmed = bool(agg["primary_source_confirmed"])
    return articles, events, mappings
