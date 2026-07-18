"""Live prior-art search → §103 loopholes: mapping, degrade, poison, isolation."""

from airtight import Disclosure, guardrails as g
from agent import prior_art
from agent.prior_art import PRIOR_ART_CONFIDENCE, _query, _to_loophole, search_prior_art

DISC = Disclosure(id="d1", title="Predictive cache eviction using access embeddings",
                  inventors=["x"], technology_class="G06F",
                  summary="a cache controller learns access-pattern embeddings", details="...")

_RAW = {"applicationNumberText": "19564989",
        "applicationMetaData": {"inventionTitle": "Adaptive cache management using predictive models"}}


def test_query_drops_stopwords_and_is_stable():
    q = _query(DISC)
    assert "cache" in q and "using" not in q  # 'using' is a stopword
    assert _query(DISC) == q  # deterministic


def test_maps_prior_art_to_distinguish_over_loophole():
    lh = _to_loophole(_RAW, DISC)
    assert lh.id == "priorart-19564989"
    assert lh.statute == "103"  # prior-art exposure is obviousness/anticipation
    assert "distinguish" in lh.remedy.lower()
    assert lh.extraction_confidence == PRIOR_ART_CONFIDENCE  # inferred, not ground truth → competes on rank
    assert "19564989" in lh.source


def test_no_key_degrades_to_empty(monkeypatch):
    monkeypatch.delenv("USPTO_API_KEY", raising=False)
    assert search_prior_art(DISC) == []  # no key, no search — never blocks a draft


def test_success_maps_all_records(monkeypatch):
    monkeypatch.setenv("USPTO_API_KEY", "dummy")
    monkeypatch.setattr(prior_art, "_search", lambda q, limit: [_RAW, _RAW])
    got = search_prior_art(DISC)
    assert len(got) == 2 and all(r.statute == "103" for r in got)


def test_quarantined_result_is_dropped(monkeypatch):
    # HiddenLayer flagged the fetched prior art as poisoned -> guarded_tool returns
    # the placeholder string instead of records -> search yields nothing.
    monkeypatch.setenv("USPTO_API_KEY", "dummy")
    monkeypatch.setattr(prior_art, "_search", lambda q, limit: g.QUARANTINE_PLACEHOLDER)
    assert search_prior_art(DISC) == []  # a poisoned reference never reaches the draft


def test_network_error_degrades_to_empty(monkeypatch):
    monkeypatch.setenv("USPTO_API_KEY", "dummy")

    def boom(q, limit):
        raise ConnectionError("USPTO down")

    monkeypatch.setattr(prior_art, "_search", boom)
    assert search_prior_art(DISC) == []


def test_ablation_harness_never_calls_prior_art():
    # Isolation by omission: the M4 harness must not import or reference prior_art,
    # or the empty-vs-warmed comparison would gain a third, uncontrolled source.
    import agent.eval.harness as h
    import inspect

    assert "prior_art" not in inspect.getsource(h)
