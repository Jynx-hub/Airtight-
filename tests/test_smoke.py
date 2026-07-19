"""Stub-mode smoke: green on a fresh clone with no .env and no network."""

import json
import pathlib
from types import SimpleNamespace

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


def _fake_live_client(monkeypatch, *, content, finish_reason, reasoning_content=""):
    """A live client that never touches the network — the response is handed in."""
    monkeypatch.setattr(config, "MODE", "live")
    message = SimpleNamespace(content=content, reasoning_content=reasoning_content)
    resp = SimpleNamespace(choices=[SimpleNamespace(message=message, finish_reason=finish_reason)])
    monkeypatch.setattr(doorway, "_client", lambda: SimpleNamespace(
        chat=SimpleNamespace(completions=SimpleNamespace(create=lambda **kw: resp))))


def test_truncated_turn_raises_instead_of_scoring_as_an_empty_draft(monkeypatch):
    # A capped reasoning-on turn spends the budget thinking and returns content=None.
    # Returning "" here would let the ablation record a failed call as a real zero.
    _fake_live_client(monkeypatch, content=None, finish_reason="length",
                      reasoning_content="thinking " * 500)
    with pytest.raises(RuntimeError, match="hit max_tokens"):
        call_model([{"role": "user", "content": "x"}], role="draft")


def test_truncation_raises_even_when_partial_content_came_back(monkeypatch):
    # A half-written draft still scores, so one arm truncating and the other not would
    # silently compare two different things (arm-invariance).
    _fake_live_client(monkeypatch, content="1. A method comprising", finish_reason="length")
    with pytest.raises(RuntimeError, match="hit max_tokens"):
        call_model([{"role": "user", "content": "x"}], role="draft")


def test_complete_turn_passes_through(monkeypatch):
    _fake_live_client(monkeypatch, content="1. A method.", finish_reason="stop")
    reply = call_model([{"role": "user", "content": "x"}], role="draft")
    assert reply.mode == "live"
    assert reply.text == "1. A method."


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
