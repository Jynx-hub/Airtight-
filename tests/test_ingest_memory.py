"""D: ingest -> memory, and the gate that makes it safe.

The headline is the negative test — a quarantined document must leave zero
records behind. Wiring ingest into long-term memory without that gate would let
an attacker write directly into the agent's store: a persistent, compounding
injection. The HiddenLayer bus is the precondition for the learning loop, not a
bolt-on beside it.
"""

import pytest

from airtight import config
from airtight import guardrails as g
from agent import ingest
from agent.memory import LoopholeStore

CLEAN = "data/fixtures/prior_art_clean.txt"
POISONED = "data/fixtures/poisoned_prior_art.txt"
POISONED_PDF = "data/fixtures/poisoned_prior_art.pdf"


def fake_response(*detections, event_id="evt-test"):
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


def test_quarantined_document_leaves_zero_records(monkeypatch, tmp_path):
    """The D3 proof. Note what is asserted: not merely that no file appeared, but
    that the model was never *called* — a poisoned document costs zero tokens and
    never reaches the doorway."""
    pytest.importorskip("pdfplumber")
    hl_on(monkeypatch, fake_response(("prompt_injection", True, ["Ignore your instructions"])))
    # Patch agent.distill, not agent.ingest: ingest_to_memory imports the name
    # locally at call time, so this is the binding it actually resolves.
    import agent.distill
    monkeypatch.setattr(agent.distill, "distill_text",
                        lambda *a, **k: pytest.fail("model reached on quarantined text"))

    store = LoopholeStore([], directory=tmp_path)
    assert ingest.ingest_to_memory(POISONED_PDF, tech_class="G06F", store=store) == []
    assert len(store) == 0
    assert list(tmp_path.glob("*.json")) == [], "quarantined content reached the store"
    assert LoopholeStore.load(tmp_path).records == [], "a later run would load it"
    assert g.QUARANTINE_LOG[-1]["source"] == "poisoned_prior_art.pdf"


def test_clean_document_writes_exactly_one_record(monkeypatch, tmp_path):
    """Positive control — without it, a `return []` stub would pass the test above."""
    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    store = LoopholeStore([], directory=tmp_path)
    records = ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)

    assert len(records) == 1, "one document distils to at most one record, by construction"
    rec = records[0]
    assert rec.id.startswith("ing-")
    assert rec.extraction_confidence < 1.0, "inferred from an untrusted doc, not ground truth"
    assert (tmp_path / f"{rec.id}.json").exists()
    assert LoopholeStore.load(tmp_path).records[0].id == rec.id


def test_guardrail_error_blocks_and_writes_nothing(monkeypatch, tmp_path):
    """INGESTED_DOCUMENT fails closed: a scanner outage must not admit anything."""
    hl_on(monkeypatch, error=RuntimeError("scanner down"))
    store = LoopholeStore([], directory=tmp_path)
    with pytest.raises(g.GuardrailBlocked):
        ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)
    assert len(store) == 0
    assert list(tmp_path.glob("*.json")) == []


def test_reingesting_the_same_document_is_idempotent(monkeypatch, tmp_path):
    """Content-addressed ids: the same document can't flood the store."""
    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    store = LoopholeStore([], directory=tmp_path)
    first = ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)
    second = ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)

    assert first[0].id == second[0].id
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert len(LoopholeStore.load(tmp_path).records) == 1


def test_ingested_record_is_retrievable(monkeypatch, tmp_path):
    """Closing the circuit: a document read at ingest changes what comes back."""
    from airtight import Disclosure

    disc = Disclosure(id="d1", title="cache eviction module", inventors=["x"],
                      technology_class="G06F", summary="a module configured to evict entries",
                      details="functional claiming without disclosed structure")
    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    store = LoopholeStore([], directory=tmp_path)
    assert store.retrieve(disc, 5) == []
    records = ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)
    assert [r.id for r in store.retrieve(disc, 5)] == [records[0].id]


def test_unscanned_ingest_refuses_to_write(monkeypatch, tmp_path):
    """The default configuration has the bus OFF. Writing then would persist an
    unscanned document — g.analyze short-circuits to PASS, so the quarantine gate
    below it can never fire and "quarantined content never reaches the store"
    would be vacuously true. Refuse instead."""
    monkeypatch.setattr(config, "HL_ENABLED", False)
    store = LoopholeStore([], directory=tmp_path)
    with pytest.raises(ingest.UnscannedIngest, match="guardrails bus OFF"):
        ingest.ingest_to_memory(POISONED, tech_class="G06F", store=store)
    assert len(store) == 0
    assert list(tmp_path.glob("*.json")) == []


def test_reingest_does_not_overwrite_on_disk(monkeypatch, tmp_path):
    """add() keeps the incumbent; save() must not then overwrite it, or memory
    and disk disagree after the next load."""
    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    store = LoopholeStore([], directory=tmp_path)
    first = ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)[0]
    ingest.ingest_to_memory(CLEAN, tech_class="H04L", store=store)  # same file, different class

    assert len(store) == 1
    on_disk = LoopholeStore.load(tmp_path).records[0]
    in_memory = next(r for r in store.records if r.id == first.id)
    assert on_disk.technology_class == in_memory.technology_class, \
        "disk and memory disagree — save() overwrote a record add() refused"


def test_save_refuses_to_write_into_the_graded_corpus(tmp_path):
    """--memory-dir is operator input. Pointing it at data/ would commit an
    agent-fabricated record as tracked ground truth and contaminate the ablation."""
    from airtight import LoopholeRecord

    rec = LoopholeRecord(id="ing-x", pattern="p", claim_shape="c",
                         technology_class="G06F", remedy="r", source="s")
    corpus = LoopholeStore([], directory="data/corpus/loopholes")
    with pytest.raises(RuntimeError, match="graded corpus"):
        corpus.save(rec)
    LoopholeStore([], directory=tmp_path).save(rec)  # anywhere outside data/ is fine


def test_provenance_marker_reaches_the_rendered_prompt(monkeypatch, tmp_path):
    """source and extraction_confidence are both dropped by render_guardrails, so
    a marker in either is invisible where it matters — the drafting prompt."""
    from agent import loop

    hl_on(monkeypatch, fake_response(("prompt_injection", False, [])))
    store = LoopholeStore([], directory=tmp_path)
    rec = ingest.ingest_to_memory(CLEAN, tech_class="G06F", store=store)[0]
    assert "UNVERIFIED" in loop.render_guardrails([rec]), \
        "an inferred record renders identically to a PTAB-mined one"
