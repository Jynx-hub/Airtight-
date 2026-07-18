"""The extraction contract shared by the PTAB miner and the ingest path."""

import hashlib

import pytest

from airtight import config
from agent.distill import (DISTILL_SYSTEM, INGEST_SYSTEM, MAX_DISTILL_CHARS,
                           _normalize_tech_class, _safe_source, distill_text, parse_json)

# sha256 of the string as it stood when it lived in data/distill_loopholes.py.
# The PTAB producer's prompt is ground-truth provenance — it must not drift
# silently just because the constant moved house.
DISTILL_SYSTEM_SHA256 = "fd4c90e7aeee70ab7d9ef99f8ba0b8e794047ea0d9f343e1e0f626ebb11b4bd7"


@pytest.fixture(autouse=True)
def force_stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


def test_distill_system_prompt_is_unchanged():
    assert hashlib.sha256(DISTILL_SYSTEM.encode()).hexdigest() == DISTILL_SYSTEM_SHA256


def test_ingest_prompt_does_not_assert_a_ptab_decision():
    """INGEST_SYSTEM must not inherit DISTILL_SYSTEM's premise. Telling the model
    a PTAB panel held claims unpatentable, about an arbitrary ingested document,
    is how a plausible-looking but fabricated record gets minted."""
    assert "PTAB" not in INGEST_SYSTEM
    assert INGEST_SYSTEM != DISTILL_SYSTEM
    # ...but both must demand the same JSON the parser and the shape expect.
    for prompt in (DISTILL_SYSTEM, INGEST_SYSTEM):
        assert '"pattern"' in prompt and '"claim_shape"' in prompt and '"remedy"' in prompt


def test_parse_json_extracts_and_rejects():
    assert parse_json('noise {"pattern": "p"} trailing') == {"pattern": "p"}
    assert parse_json("no json here") is None
    assert parse_json("{not valid json}") is None
    # A top-level array is NOT parseable — which is part of why distillation is
    # one record per call rather than a list.
    assert parse_json('[{"a": 1}, {"b": 2}]') is None


def test_distill_yields_exactly_one_record():
    records = distill_text("some prior art text about claim drafting", "doc.txt", "G06F")
    assert len(records) == 1
    assert records[0].technology_class == "G06F"


def test_record_id_is_deterministic_and_content_addressed():
    a = distill_text("identical text", "doc.txt", "G06F")[0]
    b = distill_text("identical text", "doc.txt", "G06F")[0]
    c = distill_text("different text", "doc.txt", "G06F")[0]
    assert a.id == b.id, "same input must mint the same id — re-ingest is idempotent"
    assert a.id != c.id
    assert a.id.startswith("ing-")


def test_ingested_records_are_marked_as_inferred():
    rec = distill_text("prior art text", "doc.txt", "G06F")[0]
    assert rec.extraction_confidence == 0.3, "not ground truth — must be distinguishable"
    assert "INGESTED" in rec.source
    assert "[STUB — not real]" in rec.source, "stub-mode output must say so"


def test_technology_center_class_is_rejected():
    """TC#### can never match a Disclosure's CPC class, so a record built with one
    is permanently invisible to retrieval. Fail loudly instead of minting it."""
    with pytest.raises(ValueError, match="Technology Center"):
        distill_text("text", "doc.txt", "TC2100")
    assert _normalize_tech_class("g06f") == "G06F"
    assert _normalize_tech_class("H04L2209") == "H04L"


def test_filename_cannot_inject_a_statute():
    """statute_of scans `source` too, so an attacker-named file could otherwise
    pick which diversify bucket its record lands in — and since INGEST_SYSTEM
    never asks for a statute, `source` is the usual fallback, not an edge case.

    Asserted against `statute_of` directly. An earlier version of this test only
    checked the minted record's statute, which passed for the wrong reason: the
    stub reply's pattern already contains "§112", so statute_of returned before
    ever reaching `source` and the assertion held even with no sanitizer at all.
    """
    from airtight.shapes import statute_of

    # The bare-whitespace form is the one that matters: `[§\s(]` accepts a space,
    # so stripping only "§()" leaves the match intact.
    for name in ("prior art §103.pdf", "Office Action 101.pdf", "response (102) final.pdf",
                 "112 indefiniteness notice.pdf"):
        assert statute_of(_safe_source(name)) == "", f"{name!r} still injects a statute"

    # And end-to-end: a record minted from a statute-named file must take its
    # statute from the model's pattern text, never from the filename.
    rec = distill_text("text", "Office Action 101.pdf", "G06F")[0]
    assert "101" not in rec.source
    assert rec.statute == "112", "statute must come from the pattern, not the filename"


def test_long_documents_are_truncated():
    huge = "claim drafting " * 5000
    rec = distill_text(huge, "big.pdf", "G06F")[0]
    same_prefix = distill_text(huge[:MAX_DISTILL_CHARS], "big.pdf", "G06F")[0]
    assert rec.id == same_prefix.id, "the id must digest the truncated slice actually sent"
