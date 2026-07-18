"""Concurrent sub-agent retrieval tests."""

import hashlib
import pathlib
import threading
import time

import pytest

from airtight import Disclosure, config
import airtight.doorway as doorway
from agent import loop
from agent.memory import LoopholeStore
from agent.subagents import fan_out_retrieval

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DISC = Disclosure.model_validate_json((DATA / "fixtures" / "disclosures" / "disc-0001.json").read_text())
RETRIEVED = LoopholeStore.load(DATA / "corpus" / "loopholes").retrieve(DISC, 4)


@pytest.fixture(autouse=True)
def force_stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


def test_fan_out_returns_note_per_loophole_in_order():
    notes = fan_out_retrieval(DISC, RETRIEVED)
    assert [n.loophole_id for n in notes] == [r.id for r in RETRIEVED]  # deterministic order
    assert all(n.mode == "stub" for n in notes)


def test_empty_retrieval_no_subagents():
    assert fan_out_retrieval(DISC, []) == []


def test_every_subagent_crosses_the_bus(monkeypatch):
    hops = []
    monkeypatch.setattr(doorway, "_analyze", lambda hop, payload: hops.append(hop) or payload)
    fan_out_retrieval(DISC, RETRIEVED)
    assert hops == ["input", "output"] * len(RETRIEVED)  # 2*N hops


def test_subagents_actually_run_concurrently(monkeypatch):
    peak = 0
    active = 0
    lock = threading.Lock()
    real = doorway.call_model

    def slow(messages, **kw):
        nonlocal peak, active
        with lock:
            active += 1
            peak = max(peak, active)
        time.sleep(0.02)
        with lock:
            active -= 1
        return real(messages, **kw)

    monkeypatch.setattr("agent.subagents.call_model", slow)
    fan_out_retrieval(DISC, RETRIEVED, max_workers=4)
    assert peak >= 2  # genuinely parallel, not serial


def test_fan_out_leaves_system_templates_unchanged():
    before = {n: hashlib.sha256(getattr(loop, n).encode()).hexdigest()
              for n in ("PLAN_SYSTEM", "DRAFT_SYSTEM", "CRITIQUE_SYSTEM")}
    loop.draft_patent(DISC, guardrails=RETRIEVED, fan_out=True)
    after = {n: hashlib.sha256(getattr(loop, n).encode()).hexdigest()
             for n in ("PLAN_SYSTEM", "DRAFT_SYSTEM", "CRITIQUE_SYSTEM")}
    assert before == after  # notes folded into the USER message only


def test_fan_out_off_matches_todays_transcript():
    t_off, t_on = [], []
    loop.draft_patent(DISC, guardrails=RETRIEVED, transcript=t_off, fan_out=False)
    loop.draft_patent(DISC, guardrails=RETRIEVED, transcript=t_on, fan_out=True)
    # fan_out=False draft user message has no sub-agent block; fan_out=True does
    draft_off = next(t for t in t_off if t["turn"] == "draft")["messages"][1]["content"]
    draft_on = next(t for t in t_on if t["turn"] == "draft")["messages"][1]["content"]
    assert "retrieval sub-agents" not in draft_off
    assert "retrieval sub-agents" in draft_on
