"""
models/event_classifier.py - Replaceable financial event classifier.

V1 = weighted keyword/regex rules. Anything implementing `EventClassifier`
(e.g. a zero-shot or fine-tuned model later) can be dropped in via
`CompositeEventClassifier([...])` or used directly.

Event-level classification: classify every article in the cluster, then
confidence-weighted vote -> one EventType per event.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Sequence, Tuple

from events.event_model import Article, Event, EventType


@dataclass
class Classification:
    event_type: EventType
    confidence: float                       # 0..1
    scores: Dict[str, float] = field(default_factory=dict)
    matched: List[str] = field(default_factory=list)


class EventClassifier(ABC):
    @abstractmethod
    def classify_text(self, text: str) -> Classification:
        ...

    def classify_articles(self, articles: Sequence[Article]) -> Classification:
        """Confidence-weighted vote across articles describing one event."""
        votes: Dict[str, float] = defaultdict(float)
        matched: List[str] = []
        for a in articles:
            c = self.classify_text(a.text)
            if c.event_type != EventType.OTHER:
                votes[c.event_type.value] += c.confidence
                matched.extend(c.matched)
        if not votes:
            return Classification(EventType.OTHER, 0.0, {})
        total = sum(votes.values())
        best = max(votes.items(), key=lambda kv: kv[1])[0]
        scores = {k: v / total for k, v in votes.items()}
        return Classification(EventType(best), scores[best], scores, sorted(set(matched)))

    def classify_event(self, event: Event, articles: Sequence[Article]) -> Event:
        c = self.classify_articles(articles)
        event.event_type, event.type_confidence, event.type_scores = c.event_type, c.confidence, c.scores
        return event


# (regex, weight). Weights are per-hit; strong, unambiguous phrases weigh more.
DEFAULT_RULES: Dict[EventType, List[Tuple[str, float]]] = {
    EventType.EARNINGS: [
        (r"\bq[1-4]\b.*\b(results?|earnings|profit|net income)\b", 3), (r"\b(quarterly|annual|full[- ]year) (results?|earnings|profit)\b", 3),
        (r"\b(net profit|net income|ebitda|revenue|pat)\b.*\b(rose|rises|fell|falls|jumps?|declines?|grew|up|down|crore|cr)\b", 2),
        (r"\bearnings\b", 2), (r"\bresults?\b", 1), (r"\b(beats?|misses?) (estimates|expectations|street)\b", 3),
        (r"\bfy ?\d{2}\b.*\b(profit|results)\b", 2), (r"\beps\b", 2),
    ],
    EventType.GUIDANCE: [
        (r"\bguidance\b", 3), (r"\b(raises?|cuts?|lowers?|maintains?|reiterates?) (its )?(fy|full[- ]year)?.{0,15}(outlook|forecast|target)\b", 3),
        (r"\boutlook\b", 2), (r"\bexpects? (revenue|growth|profit|margins?)\b", 2), (r"\bforecasts?\b", 1),
    ],
    EventType.MERGER_ACQUISITION: [
        (r"\b(merger|merges?|amalgamation|takeover|acquisition|acquires?|acquired|buyout|demerger)\b", 3),
        (r"\bto (buy|acquire|purchase) (a )?(\d+%|majority|controlling|stake)", 3), (r"\bstake (sale|purchase|acquisition)\b", 2),
        (r"\b(joint venture|jv)\b", 1), (r"\bopen offer\b", 2),
    ],
    EventType.DIVIDEND: [
        (r"\bdividends?\b", 3), (r"\b(interim|final|special) dividend\b", 4), (r"\brecord date\b.*\bdividend\b", 2), (r"\bpayout\b", 1),
    ],
    EventType.BUYBACK: [
        (r"\bbuy[- ]?backs?\b", 4), (r"\brepurchase (of )?(shares|stock)\b", 4), (r"\bshare repurchase\b", 4),
    ],
    EventType.CAPITAL_RAISE: [
        (r"\b(qip|fpo|ipo|rights issue|preferential (issue|allotment)|follow[- ]on offer)\b", 4),
        (r"\braises? (rs\.?|inr|₹|\$)?\s?[\d,.]+\s?(crore|cr|billion|million|bn|mn)\b.*\b(equity|capital|funds?)\b", 3),
        (r"\b(equity|capital) raise\b", 3), (r"\bfundrais(e|ing)\b", 2), (r"\bshare sale\b", 2),
    ],
    EventType.DEBT_FINANCING: [
        (r"\b(ncds?|debentures?|bonds?|term loan|credit facility|loan|borrowings?|refinanc\w+|debt)\b", 2),
        (r"\b(issues?|raises?) .{0,30}\b(bonds?|ncds?|debentures?)\b", 3), (r"\bcredit rating\b", 2), (r"\bdowngrades? (credit|debt|bonds?)\b", 2),
    ],
    EventType.MANAGEMENT_CHANGE: [
        (r"\b(appoints?|appointed|names?|resigns?|resigned|steps? down|quits?|succession|retires?)\b.{0,40}\b(ceo|cfo|coo|cto|chairman|chair|md|managing director|director|president|chief)\b", 4),
        (r"\b(ceo|cfo|chairman|md|managing director)\b.{0,30}\b(appointed|resigns?|exits?|steps? down|quits?|named)\b", 4), (r"\bmanagement (change|reshuffle)\b", 3),
    ],
    EventType.PRODUCT_SERVICE: [
        (r"\b(launch(es|ed)?|unveils?|introduces?|rolls? out|debuts?)\b", 2), (r"\b(new (product|service|model|variant|platform|app))\b", 2),
        (r"\bproduct (launch|recall)\b", 3), (r"\brecalls?\b", 2),
    ],
    EventType.EXPANSION: [
        (r"\bexpan(ds|sion|ding)\b", 3), (r"\b(opens?|inaugurates?|to open|setting up|sets up) (a )?(new )?(plant|factory|facility|store|stores|outlets?|branch(es)?|office|centre|center)\b", 3),
        (r"\benters? (the )?\w+ market\b", 3), (r"\bnew (plant|facility|capacity|market)\b", 2),
    ],
    EventType.CAPEX: [
        (r"\bcapex\b", 4), (r"\bcapital expenditure\b", 4), (r"\bto invest (rs\.?|inr|₹|\$)?\s?[\d,.]+\s?(crore|cr|billion|million|bn|mn)\b", 3), (r"\binvestment of (rs\.?|inr|₹|\$)?\s?[\d,.]+", 2),
        (r"\bcapacity (addition|expansion)\b", 3),
    ],
    EventType.MAJOR_CONTRACT: [
        (r"\b(wins?|bags?|secures?|lands?|awarded|receives?|clinches)\b.{0,40}\b(order|orders|contract|deal|tender|mandate)\b", 4),
        (r"\b(order win|order book|letter of (award|intent)|loi)\b", 3), (r"\bsigns? (a )?(\$|rs\.?|₹)?.{0,15}(deal|agreement|contract|mou)\b", 2),
    ],
    EventType.REGULATION: [
        (r"\b(sebi|rbi|cci|irdai|trai|fda|sec|dgca|nclt|government|ministry)\b.{0,50}\b(approves?|approval|norms?|rules?|regulations?|guidelines?|ban|notif\w+|clearance|licen[sc]e|penal(ty|ties)|fines?)\b", 3),
        (r"\bregulat(ory|ion|ions|or)\b", 2), (r"\b(approval|nod) from\b", 2), (r"\b(tax|tariff|duty) (hike|cut|change|imposed)\b", 2), (r"\bcompliance\b", 1),
    ],
    EventType.LITIGATION: [
        (r"\b(lawsuit|sues?|sued|court|tribunal|petition|litigation|verdict|ruling|high court|supreme court|arbitration|class action|injunction)\b", 3),
        (r"\b(wins?|loses?) (case|appeal)\b", 3),
    ],
    EventType.INVESTIGATION: [
        (r"\b(probe|investigation|raids?|show[- ]cause notice|inquiry|sfio|cbi)\b", 3),
    ],
    EventType.FRAUD: [
        (r"\b(fraud|fraudulent|scam|embezzlement|accounting irregularit\w+|misappropriation|money laundering|ponzi|forgery|insider trading|diversion of funds|siphon\w*|short[- ]seller report|whistleblower)\b", 5),
    ],
    EventType.ANALYST_ACTION: [
        (r"\b(upgrades?|downgrades?|initiates? coverage|reiterates?|maintains?) .{0,30}\b(buy|sell|hold|neutral|outperform|underperform|overweight|underweight|accumulate|reduce)\b", 4),
        (r"\b(price target|target price|tp)\b", 3), (r"\b(brokerage|analysts?|jefferies|goldman|morgan stanley|motilal|nomura|cl?sa|kotak|icici securities|hdfc securities)\b.{0,40}\b(rating|target|recommend\w*|buy|sell)\b", 3),
        (r"\b(buy|sell|hold) rating\b", 3),
    ],
    EventType.SUBSIDIARY_EVENT: [
        (r"\bsubsidiar(y|ies)\b", 3), (r"\bwholly[- ]owned\b", 3), (r"\b(arm|unit)\b.{0,20}\b(ipo|listing|stake|incorporates?|raises?)\b", 2), (r"\bstep[- ]down subsidiary\b", 3),
    ],
    EventType.CORPORATE_ACTION: [
        (r"\b(stock split|share split|bonus (issue|shares?)|sub[- ]?division|consolidation of shares|delisting|record date|ex[- ]date|name change|rename[sd]?|rebrand\w*|reclassification|scheme of arrangement|spin[- ]?off)\b", 4),
    ],
}

# When two types tie, prefer the more specific / higher-signal one.
TIE_PRIORITY: List[EventType] = [
    EventType.FRAUD, EventType.INVESTIGATION, EventType.LITIGATION, EventType.MERGER_ACQUISITION,
    EventType.BUYBACK, EventType.DIVIDEND, EventType.EARNINGS, EventType.GUIDANCE, EventType.CAPITAL_RAISE,
    EventType.MANAGEMENT_CHANGE, EventType.MAJOR_CONTRACT, EventType.ANALYST_ACTION, EventType.CORPORATE_ACTION,
    EventType.SUBSIDIARY_EVENT, EventType.CAPEX, EventType.EXPANSION, EventType.REGULATION,
    EventType.DEBT_FINANCING, EventType.PRODUCT_SERVICE,
]


class KeywordRuleClassifier(EventClassifier):
    """Weighted regex rules. Rules are plain data -> configurable at construction."""

    def __init__(self, rules: Optional[Dict[EventType, List[Tuple[str, float]]]] = None,
                 min_score: float = 2.0, title_boost: float = 1.5):
        self.min_score = min_score
        self.title_boost = title_boost
        self._rules = {et: [(re.compile(p, re.I), w) for p, w in pats]
                       for et, pats in (rules or DEFAULT_RULES).items()}

    def classify_text(self, text: str) -> Classification:
        text = text or ""
        # first sentence ~ headline gets a boost
        head = re.split(r"(?<=[.!?])\s", text, maxsplit=1)[0]
        scores: Dict[EventType, float] = {}
        matched: Dict[EventType, List[str]] = defaultdict(list)
        for et, pats in self._rules.items():
            s = 0.0
            for rx, w in pats:
                m = rx.search(text)
                if m:
                    s += w * (self.title_boost if rx.search(head) else 1.0)
                    matched[et].append(m.group(0)[:60])
            if s > 0:
                scores[et] = s
        if not scores or max(scores.values()) < self.min_score:
            return Classification(EventType.OTHER, 0.0, {})
        top = max(scores.values())
        tied = [et for et, s in scores.items() if s == top]
        best = min(tied, key=lambda e: TIE_PRIORITY.index(e) if e in TIE_PRIORITY else 99)
        total = sum(scores.values())
        norm = {et.value: s / total for et, s in scores.items()}
        return Classification(best, norm[best.value], norm, matched[best])


class CompositeEventClassifier(EventClassifier):
    """
    Chain classifiers: use the first whose confidence >= threshold, else the best one.
    Lets a semantic/ML classifier be layered over keyword rules without code changes.
    """

    def __init__(self, classifiers: Sequence[EventClassifier], threshold: float = 0.5):
        self.classifiers = list(classifiers)
        self.threshold = threshold

    def classify_text(self, text: str) -> Classification:
        best: Optional[Classification] = None
        for c in self.classifiers:
            r = c.classify_text(text)
            if r.event_type != EventType.OTHER and r.confidence >= self.threshold:
                return r
            if best is None or r.confidence > best.confidence:
                best = r
        return best or Classification(EventType.OTHER, 0.0, {})
