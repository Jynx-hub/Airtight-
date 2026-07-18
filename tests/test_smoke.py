"""Stub-mode smoke: green on a fresh clone with no .env and no network."""

import json
import pathlib

import pytest

import airtight.doorway as doorway
from airtight import Disclosure, Draft, EvalResult, LoopholeRecord, call_model
from airtight import config

FIXTURE = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_disclosure.json"


@pytest.fixture(autouse=True)
def force_stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


def test_stub_replies_differ_by_role(monkeypatch):
    # stub mode must short-circuit before any client exists — make construction fatal
    monkeypatch.setattr(doorway, "_client", lambda: pytest.fail("client constructed in stub mode"))
    tool = call_model([{"role": "user", "content": "x"}], role="tool")
    draft = call_model([{"role": "user", "content": "x"}], role="draft")
    assert tool.mode == draft.mode == "stub"
    assert tool.text != draft.text
    json.loads(tool.text)  # tool stub is parseable JSON


def test_analyze_fires_on_both_hops(monkeypatch):
    hops = []

    def spy(hop, payload):
        hops.append(hop)
        return payload

    monkeypatch.setattr(doorway, "_analyze", spy)
    call_model([{"role": "user", "content": "x"}], role="draft")
    assert hops == ["input", "output"]


def test_stream_yields_chunks():
    chunks = list(call_model([{"role": "user", "content": "x"}], role="draft", stream=True))
    assert len(chunks) > 1
    assert "".join(chunks).strip() == doorway.STUB_REPLIES["draft"]


def test_shapes_roundtrip_via_fixture():
    disclosure = Disclosure.model_validate_json(FIXTURE.read_text())
    assert disclosure.technology_class == "G06F"

    samples = [
        disclosure,
        LoopholeRecord(
            id="lh-1", pattern="antecedent-basis gap", claim_shape="the widget",
            technology_class="G06F", remedy="introduce antecedent", source="PTAB IPR2020-0001",
        ),
        Draft(disclosure_id=disclosure.id, claims=["1. A method..."], specification="spec"),
        EvalResult(
            disclosure_id=disclosure.id, condition="empty", loopholes_caught=2,
            checklist_size=10, drafting_seconds=42.0, defect_count=5,
        ),
    ]
    for model in samples:
        assert type(model).model_validate_json(model.model_dump_json()) == model


def test_loop_runs_in_stub_mode():
    from agent.loop import draft_patent

    draft = draft_patent(Disclosure.model_validate_json(FIXTURE.read_text()))
    assert draft.disclosure_id == "disc-0001"
    assert len(draft.claims) >= 2  # stub draft has two numbered claims
    assert draft.critique_notes
