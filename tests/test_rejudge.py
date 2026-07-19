"""Re-judging banked drafts — provenance and pairing.

`rejudge` exists to repair a run whose scoring was wrong without paying to
re-draft it. That makes two properties load-bearing:

- it must be **honest about what it did** — a re-judge is not a fresh ablation,
  and its fingerprint has to say so, including the SHA of the run it re-scored;
- it must **pair arms correctly**, because `_pair_deltas` buckets by position and
  a mis-ordered empty/warmed pair silently compares a disclosure against itself.

Runs in stub mode: the judge returns closed=False and no defects there, so these
assert plumbing and provenance, not a delta. See `test_claim_parsing.py` for the
parser invariant that made the repair necessary.
"""

import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.eval.rejudge import final_reply, rejudge_run  # noqa: E402


def _transcript(disclosure_id: str, condition: str, reply: str, caught: int = 0) -> dict:
    return {
        "run": 0,
        "condition": condition,
        "disclosure_id": disclosure_id,
        "retrieved_ids": [],
        "transcript": [
            {"turn": "plan", "messages": [], "reply": "a plan"},
            {"turn": "draft", "messages": [], "reply": "an early draft"},
            {"turn": "revise-1", "messages": [], "reply": reply},
        ],
        "verdicts": [],
        "defects": [],
        "result": {
            "disclosure_id": disclosure_id,
            "condition": condition,
            "loopholes_caught": caught,
            "checklist_size": 1,
            "drafting_seconds": 42.5,
            "defect_count": 0,
        },
    }


DRAFT = "1. A system comprising a processor configured to do the thing.\n\n2. The system of claim 1.\n"


@pytest.fixture
def banked(tmp_path):
    """A minimal source run: one disclosure, both arms, plus its checklist."""
    run = tmp_path / "run"
    (run / "transcripts").mkdir(parents=True)
    for cond in ("empty", "warmed"):
        (run / "transcripts" / f"run0-d-1-{cond}.json").write_text(
            json.dumps(_transcript("d-1", cond, DRAFT))
        )
    (run / "results.json").write_text(json.dumps({
        "fingerprint": {"git_sha": "deadbeefcafe", "k": 5, "runs": 1, "draft_gen": {"seed": 1234}},
        "corpus_size": 167,
    }))

    data_root = tmp_path / "data"
    (data_root / "checklists").mkdir(parents=True)
    (data_root / "checklists" / "d-1.json").write_text(json.dumps([{
        "id": "lp-1", "pattern": "§101 abstract idea", "claim_shape": "x",
        "technology_class": "G06F", "remedy": "recite a specific machine",
        "source": "test", "statute": "101", "extraction_confidence": 0.9,
    }]))
    return run, data_root


def test_final_reply_takes_the_last_turn_that_has_one():
    """Revise rounds vary per arm, so the post-revision draft is the LAST reply,
    not a fixed index."""
    record = _transcript("d-1", "empty", "the final text")
    assert final_reply(record) == "the final text"


def test_fingerprint_marks_this_as_a_rejudge_not_a_fresh_run(banked, tmp_path):
    run, data_root = banked
    payload = json.loads(rejudge_run(run, data_root, tmp_path / "out").read_text())
    fp = payload["fingerprint"]

    assert fp["kind"] == "rejudge"
    assert fp["drafts_regenerated"] is False
    assert fp["source_git_sha"] == "deadbeefcafe", "must name the run it re-scored"
    assert fp["git_sha_captured"] == "run-start", (
        "capturing at write time is how 20260718-183817 got a SHA post-dating its own code"
    )


def test_drafting_seconds_are_carried_not_reinvented(banked, tmp_path):
    """Nothing was re-drafted, so a fresh timing here would be a fabricated
    measurement."""
    run, data_root = banked
    payload = json.loads(rejudge_run(run, data_root, tmp_path / "out").read_text())
    assert {r["drafting_seconds"] for r in payload["results"]} == {42.5}


def test_arms_pair_empty_before_warmed(banked, tmp_path):
    """_pair_deltas buckets by (disclosure_id, i // 2) — order is the pairing."""
    run, data_root = banked
    payload = json.loads(rejudge_run(run, data_root, tmp_path / "out").read_text())
    assert [r["condition"] for r in payload["results"]] == ["empty", "warmed"]
    assert len(payload["pairs"]) == 1
    assert payload["pairs"][0]["disclosure_id"] == "d-1"


def test_scoring_asymmetry_is_reported_per_pair(banked, tmp_path):
    """The metric that revealed the original defect ships with every re-judge, so
    a future asymmetry is visible instead of silently skewing a delta."""
    run, data_root = banked
    payload = json.loads(rejudge_run(run, data_root, tmp_path / "out").read_text())
    asym = payload["scoring_asymmetry"]
    assert len(asym) == 1 and asym[0]["disclosure_id"] == "d-1"
    assert asym[0]["ratio"] == 1.0, "identical drafts must score identically"
