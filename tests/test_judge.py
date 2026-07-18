"""Defect-judge grounding: hallucinated / duplicate defects must not be counted."""

import pytest

from airtight import config
from agent.eval import judge


@pytest.fixture(autouse=True)
def stub_mode(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


CLAIMS = "1. A method comprising: receiving a data stream; and evicting the entry with the furthest predicted next access."


def _fake_reply(defects):
    class R:
        text = __import__("json").dumps({"defects": defects})
        mode = "live"
    return R()


def test_ungrounded_defects_are_dropped(monkeypatch):
    # one real quote (present in CLAIMS) + one hallucinated (not present)
    monkeypatch.setattr(judge, "call_model", lambda *a, **k: _fake_reply([
        {"section": "112", "claim": 1, "type": "indefinite", "quote": "furthest predicted next access"},
        {"section": "103", "claim": 1, "type": "obvious", "quote": "a quantum flux capacitor never claimed"},
    ]))
    defects = judge.count_defects(CLAIMS, "spec")
    assert len(defects) == 1 and defects[0].section == "112"


def test_duplicate_defects_deduped(monkeypatch):
    monkeypatch.setattr(judge, "call_model", lambda *a, **k: _fake_reply([
        {"section": "112", "claim": 1, "type": "indefinite", "quote": "receiving a data stream"},
        {"section": "112", "claim": 1, "type": "indefinite (dup)", "quote": "Receiving a  data stream"},
    ]))
    assert len(judge.count_defects(CLAIMS, "spec")) == 1  # normalized dedup


def test_over_listing_is_capped(monkeypatch):
    grounded = [{"section": "112", "claim": 1, "type": f"d{i}", "quote": w}
                for i, w in enumerate(CLAIMS.replace(".", "").split()) if len(w) > 3]
    monkeypatch.setattr(judge, "call_model", lambda *a, **k: _fake_reply(grounded))
    assert len(judge.count_defects(CLAIMS, "spec")) <= judge.DEFECT_CAP


def test_stub_returns_no_defects():
    assert judge.count_defects(CLAIMS, "spec") == []  # stub never fabricates
