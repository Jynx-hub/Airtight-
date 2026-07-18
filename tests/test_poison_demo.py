"""The Track-2 poison demo must fire all five hops and quarantine the doc."""

import pytest

from airtight import config
from airtight import guardrails as g


@pytest.fixture(autouse=True)
def clean(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODE", "stub")
    monkeypatch.setattr(g, "_SECURITY_DIR", tmp_path)
    monkeypatch.setattr(config, "HL_ENABLED", False)
    g.AUDIT_LOG.clear()
    g.QUARANTINE_LOG.clear()


def test_all_five_hops_fire_and_poison_quarantined(monkeypatch):
    from agent import poison_demo

    monkeypatch.setattr("sys.argv", ["poison_demo", "--fake"])
    rc = poison_demo.main()

    assert rc == 0  # main returns 0 only when all five hops fired
    fired = {r["hop"] for r in g.AUDIT_LOG}
    assert fired == {h.value for h in g.Hop}  # exactly the five interaction types
    assert len(g.QUARANTINE_LOG) == 1  # the poisoned document, nothing else
    assert g.QUARANTINE_LOG[0]["hop"] == "ingested_document"


def test_guarded_prior_art_tool_crosses_bus(monkeypatch):
    from agent import poison_demo

    poison_demo._install_fake()  # clean responses
    monkeypatch.setattr(config, "HL_ENABLED", True)
    result = poison_demo.prior_art_search("cache eviction")
    assert "US10111222" in result  # clean result passed through
    hops = {r["hop"] for r in g.AUDIT_LOG}
    assert {"tool_call", "tool_result"} <= hops
