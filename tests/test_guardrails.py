"""M2 guardrails policy tests — no network, no hiddenlayer-sdk needed.

All policy logic is exercised by monkeypatching guardrails._raw_analyze (the
single SDK touchpoint) with canned response dicts in the documented shape.
"""

import sys

import pytest

from airtight import config
from airtight import guardrails as g
from airtight import call_model

POISONED = "data/fixtures/poisoned_prior_art.txt"


def fake_response(*detections, event_id="evt-test"):
    """Build the documented response shape from (name, detected, matches) tuples."""
    return {
        "metadata": {"event_id": event_id},
        "analysis": [
            {"name": name, "phase": "input", "detected": detected,
             "findings": {"matches": list(matches)}}
            for name, detected, matches in detections
        ],
    }


@pytest.fixture(autouse=True)
def clean_state(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODE", "stub")
    monkeypatch.setattr(g, "_SECURITY_DIR", tmp_path / "security")
    g.AUDIT_LOG.clear()
    g.QUARANTINE_LOG.clear()


def hl_on(monkeypatch, response=None, error=None):
    monkeypatch.setattr(config, "HL_ENABLED", True)

    def raw(text, phase):
        if error:
            raise error
        return response

    monkeypatch.setattr(g, "_raw_analyze", raw)


# ---------- disabled short-circuit ----------

def test_disabled_short_circuits_no_import(monkeypatch):
    monkeypatch.setattr(config, "HL_ENABLED", False)
    monkeypatch.setattr(g, "_raw_analyze", lambda *a: pytest.fail("network in off mode"))
    for hop in g.Hop:
        verdict = g.analyze(hop, "hello")
        assert verdict.action is g.Action.PASS and verdict.mode == "off"
    assert "hiddenlayer" not in sys.modules


# ---------- detected outcomes per hop ----------

def test_clean_passes_every_hop(monkeypatch):
    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    for hop in g.Hop:
        verdict = g.analyze(hop, "clean text")
        assert verdict.action is g.Action.PASS and verdict.text == "clean text"


def test_pii_in_output_redacts_and_continues(monkeypatch):
    hl_on(monkeypatch, fake_response(("pii", True, ["555-0100"])))
    verdict = g.analyze(g.Hop.MODEL_RESPONSE, "call 555-0100 now")
    assert verdict.action is g.Action.REDACT
    assert "555-0100" not in verdict.text and "[REDACTED]" in verdict.text


def test_redaction_falls_back_on_unknown_matches_shape(monkeypatch):
    hl_on(monkeypatch, fake_response(("pii", True, [{"weird": "shape"}])))
    verdict = g.analyze(g.Hop.MODEL_RESPONSE, "some text with pii")
    assert verdict.action is g.Action.REDACT
    assert verdict.text.startswith("[REDACTED: pii detected")


def test_injection_in_ingested_doc_quarantines_and_logs(monkeypatch):
    hl_on(monkeypatch, fake_response(("prompt_injection", True, ["Ignore your instructions"])))
    verdict = g.analyze(g.Hop.INGESTED_DOCUMENT, "doc text", source="evil.pdf")
    assert verdict.action is g.Action.QUARANTINE and verdict.text == ""
    assert g.QUARANTINE_LOG[-1]["source"] == "evil.pdf"
    assert "prompt_injection" in g.QUARANTINE_LOG[-1]["categories"]


def test_injection_in_tool_call_blocks_before_execution(monkeypatch):
    hl_on(monkeypatch, fake_response(("prompt_injection", True, [])))
    calls = []

    @g.guarded_tool
    def send_data(dest):
        calls.append(dest)

    with pytest.raises(g.GuardrailBlocked):
        send_data("evil.example")
    assert calls == []  # the tool never ran


def test_poisoned_tool_result_quarantined(monkeypatch):
    monkeypatch.setattr(config, "HL_ENABLED", True)
    responses = iter([
        fake_response(("prompt_injection", False, [])),  # tool_call: clean
        fake_response(("prompt_injection", True, [])),  # tool_result: poisoned
    ])
    monkeypatch.setattr(g, "_raw_analyze", lambda text, phase: next(responses))

    @g.guarded_tool
    def search(q):
        return "poisoned result"

    assert search("cache eviction") == g.QUARANTINE_PLACEHOLDER


def test_unknown_detected_category_uses_hop_default(monkeypatch):
    hl_on(monkeypatch, fake_response(("dos", True, [])))
    assert g.analyze(g.Hop.USER_PROMPT, "x").action is g.Action.PASS
    assert g.analyze(g.Hop.INGESTED_DOCUMENT, "x").action is g.Action.QUARANTINE
    with pytest.raises(g.GuardrailBlocked):
        g.analyze(g.Hop.TOOL_CALL, "x")


# ---------- fail modes ----------

def test_api_error_fail_open_on_prompt_and_response(monkeypatch):
    hl_on(monkeypatch, error=ConnectionError("HL unreachable"))
    for hop in (g.Hop.USER_PROMPT, g.Hop.MODEL_RESPONSE, g.Hop.TOOL_RESULT):
        verdict = g.analyze(hop, "text")
        assert verdict.action is g.Action.PASS and "HL unreachable" in verdict.error


def test_api_error_fail_closed_on_tool_call_and_ingest(monkeypatch):
    hl_on(monkeypatch, error=ConnectionError("HL unreachable"))
    for hop in (g.Hop.TOOL_CALL, g.Hop.INGESTED_DOCUMENT):
        with pytest.raises(g.GuardrailBlocked):
            g.analyze(hop, "text")


def test_malformed_response_follows_hop_fail_mode(monkeypatch):
    for bad in ({}, {"analysis": "nope"}, {"analysis": [{"name": "x"}]}):
        hl_on(monkeypatch, response=bad)
        assert g.analyze(g.Hop.USER_PROMPT, "x").action is g.Action.PASS
        with pytest.raises(g.GuardrailBlocked):
            g.analyze(g.Hop.TOOL_CALL, "x")


# ---------- integration ----------

def test_doorway_routes_hops_through_bus(monkeypatch):
    monkeypatch.setattr(config, "HL_ENABLED", True)
    seen = []

    def raw(text, phase):
        seen.append(phase)
        return fake_response(("pii", True, ["A. Example"]))

    monkeypatch.setattr(g, "_raw_analyze", raw)
    reply = call_model([{"role": "user", "content": "draft for A. Example"}], role="draft")
    assert seen == ["input", "output"]  # user_prompt then model_response
    # pii detected but match not found in text -> whole-text redaction fallback applied
    assert reply.text.startswith("[REDACTED") and "cache" not in reply.text


def test_ingest_fixture_end_to_end(monkeypatch):
    from agent.ingest import ingest_document

    hl_on(monkeypatch, fake_response(("prompt_injection", True, ["Ignore your instructions"])))
    assert ingest_document(POISONED) is None
    assert g.QUARANTINE_LOG[-1]["source"] == "poisoned_prior_art.txt"

    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    text = ingest_document(POISONED)
    assert text is not None and "ADAPTIVE CACHE MANAGEMENT" in text
