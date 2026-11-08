import pytest
from events.event_model import Article, EventType, Event
from models.event_classifier import (CompositeEventClassifier, EventClassifier, Classification,
                                     KeywordRuleClassifier)

C = KeywordRuleClassifier()


@pytest.mark.parametrize("text,expected", [
    ("Reliance Q2 results: net profit rises 12% to Rs 18,000 crore", EventType.EARNINGS),
    ("TCS raises FY26 revenue guidance on strong deal pipeline", EventType.GUIDANCE),
    ("Tata Motors to acquire 51% stake in rival EV maker", EventType.MERGER_ACQUISITION),
    ("Infosys declares interim dividend of Rs 21 per share", EventType.DIVIDEND),
    ("Infosys board approves share buyback of Rs 9,000 crore", EventType.BUYBACK),
    ("Company launches QIP to raise Rs 5,000 crore", EventType.CAPITAL_RAISE),
    ("Adani Ports issues NCDs worth Rs 1,000 crore", EventType.DEBT_FINANCING),
    ("Wipro CEO resigns, board appoints interim chief executive", EventType.MANAGEMENT_CHANGE),
    ("Maruti launches new compact SUV model", EventType.PRODUCT_SERVICE),
    ("Dmart expands with 50 new stores across south India", EventType.EXPANSION),
    ("L&T announces capex of Rs 3,000 crore for new capacity", EventType.CAPEX),
    ("L&T bags mega order worth Rs 7,000 crore from state government", EventType.MAJOR_CONTRACT),
    ("SEBI approves new norms for listed entities", EventType.REGULATION),
    ("Supreme Court dismisses petition against company in tax litigation", EventType.LITIGATION),
    ("CBI raids offices of promoter in bank loan probe", EventType.INVESTIGATION),
    ("Short-seller report alleges accounting irregularities and fraud", EventType.FRAUD),
    ("Jefferies upgrades stock to buy, raises price target to Rs 3,200", EventType.ANALYST_ACTION),
    ("Company incorporates wholly-owned subsidiary in Singapore", EventType.SUBSIDIARY_EVENT),
    ("Board approves 1:1 bonus issue and stock split", EventType.CORPORATE_ACTION),
    ("Sensex ends flat as markets await cues", EventType.OTHER),
])
def test_classification(text, expected):
    assert C.classify_text(text).event_type == expected


def test_all_types_covered_by_enum():
    required = {"EARNINGS", "GUIDANCE", "MERGER_ACQUISITION", "DIVIDEND", "BUYBACK", "CAPITAL_RAISE",
                "DEBT_FINANCING", "MANAGEMENT_CHANGE", "PRODUCT_SERVICE", "EXPANSION", "CAPEX",
                "MAJOR_CONTRACT", "REGULATION", "LITIGATION", "INVESTIGATION", "FRAUD",
                "ANALYST_ACTION", "SUBSIDIARY_EVENT", "CORPORATE_ACTION", "OTHER"}
    assert required == {e.value for e in EventType}


def test_confidence_bounds_and_other_has_zero():
    r = C.classify_text("Infosys declares interim dividend")
    assert 0 < r.confidence <= 1
    assert C.classify_text("hello world").confidence == 0.0


def _a(title, url):
    return Article.from_raw({"ticker": "X", "title": title, "url": url, "source": url})


def test_event_level_vote_majority_wins():
    arts = [_a("Q2 results: net profit rises", "1"), _a("Q2 earnings beat estimates", "2"),
            _a("Stock jumps after results", "3")]
    ev = Event(event_id="E", ticker="X", title="t")
    C.classify_event(ev, arts)
    assert ev.event_type == EventType.EARNINGS and ev.type_confidence > 0.5


def test_classifier_is_replaceable():
    class AlwaysFraud(EventClassifier):
        def classify_text(self, text): return Classification(EventType.FRAUD, 0.9)
    ev = Event(event_id="E", ticker="X", title="t")
    AlwaysFraud().classify_event(ev, [_a("anything", "1")])
    assert ev.event_type == EventType.FRAUD


def test_composite_falls_back_to_next():
    class Weak(EventClassifier):
        def classify_text(self, text): return Classification(EventType.OTHER, 0.0)
    comp = CompositeEventClassifier([Weak(), C], threshold=0.3)
    assert comp.classify_text("Infosys declares interim dividend").event_type == EventType.DIVIDEND


def test_custom_rules_configurable():
    k = KeywordRuleClassifier(rules={EventType.DIVIDEND: [(r"\bpayday\b", 5)]})
    assert k.classify_text("Big payday for holders").event_type == EventType.DIVIDEND
