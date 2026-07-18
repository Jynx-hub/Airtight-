"""B1 — the revise turn: self-correction, and its ablation-safety invariants."""

import pathlib

import pytest

from airtight import Disclosure, config
from agent import loop
from agent.loop import draft_patent

DISC = Disclosure.model_validate_json(
    (pathlib.Path(__file__).resolve().parent.parent
     / "data" / "fixtures" / "disclosures" / "disc-0001.json").read_text()
)


class _Reply:
    def __init__(self, text):
        self.text, self.mode = text, "live"


def _script(critique_always_defective=False):
    """Route by system-prompt identity: plan / draft / critique / revise."""
    def fake(messages, role="draft", **kw):
        sysc = messages[0]["content"]
        if "planning module" in sysc:
            return _Reply("{}")
        if "revising your own draft" in sysc:
            return _Reply("1. A revised method with proper antecedent basis.\nSpec: revised text.")
        if "hostile patent examiner" in sysc:
            return _Reply("- §112 antecedent-basis gap in claim 1")  # a material defect
        return _Reply("1. A method for X.\nSpec: original draft text.")  # draft
    return fake


@pytest.fixture(autouse=True)
def stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


def test_stub_does_no_revision():
    # real stub replies carry no defect keyword -> material_defects empty -> 0 revises
    t = []
    d = draft_patent(DISC, transcript=t)
    assert not any(turn["turn"].startswith("revise") for turn in t)
    assert "stub draft" in d.specification  # unchanged, byte-identical to pre-B1


def test_revise_runs_and_specification_is_post_revision(monkeypatch):
    monkeypatch.setattr(loop, "call_model", _script())
    t = []
    d = draft_patent(DISC, transcript=t, max_revise_rounds=1)
    assert any(turn["turn"] == "revise-1" for turn in t)  # a revise turn happened
    assert "revised" in d.specification and "original" not in d.specification  # post-revision text
    assert d.critique_notes == ["- §112 antecedent-basis gap in claim 1"]  # the INITIAL critique


def test_revise_stops_at_cap(monkeypatch):
    monkeypatch.setattr(loop, "call_model", _script(critique_always_defective=True))
    t = []
    draft_patent(DISC, transcript=t, max_revise_rounds=2)
    revises = [turn["turn"] for turn in t if turn["turn"].startswith("revise")]
    assert revises == ["revise-1", "revise-2"]  # exactly the cap, then stops


def test_zero_rounds_is_draft_only(monkeypatch):
    monkeypatch.setattr(loop, "call_model", _script())
    t = []
    draft_patent(DISC, transcript=t, max_revise_rounds=0)
    assert not any(turn["turn"].startswith("revise") for turn in t)


def test_scaffold_proof_covers_revise_template():
    from agent.eval.harness import scaffold_proof

    proof = scaffold_proof([])
    assert "REVISE_SYSTEM" in proof["templates_sha256"]  # the audit trail includes the new template
