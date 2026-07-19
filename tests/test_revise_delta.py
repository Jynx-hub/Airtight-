"""Within-run defect reduction, read off banked --revise-rounds 2 transcripts.

No --revise-rounds 2 run exists yet, so these build the transcript shape the harness
writes. The point is that the analysis is ready and correct *before* the GPU window,
not debugged after it against data that cost credit to produce.
"""

import json

import pytest

from agent.eval.revise_delta import analyse_run, arm_delta

# Three lines that material_defects keeps (each names a statute or a defect keyword)
# and one it drops, so a passing test also pins the filtering, not just the arithmetic.
CRITIQUE_3 = (
    "Here are the defects:\n"
    "# Findings\n"
    "- §112 antecedent-basis gap in claim 1\n"
    "- §101 abstract idea: the claim is do-it-on-a-computer\n"
    "- §103 obvious over the cited combination\n"
)
CRITIQUE_1 = "- §112 antecedent-basis gap in claim 1\n"


def _record(disclosure_id, condition, critiques):
    """A transcript record in the shape agent/eval/harness.py writes."""
    transcript = [{"turn": "plan", "reply": "{}"}, {"turn": "draft", "reply": "1. A method."}]
    for name, text in critiques.items():
        transcript.append({"turn": name, "reply": text})
    return {"disclosure_id": disclosure_id, "condition": condition, "transcript": transcript}


def _run_dir(tmp_path, records):
    d = tmp_path / "run"
    (d / "transcripts").mkdir(parents=True)
    for i, rec in enumerate(records):
        (d / "transcripts" / f"run0-{rec['disclosure_id']}-{rec['condition']}.json").write_text(
            json.dumps(rec))
    (d / "results.json").write_text(json.dumps(
        {"fingerprint": {"git_sha": "abc123", "memory_py_sha": "b44efec3", "revise_rounds": 2,
                         "mode": "live"}}))
    return d


def test_counts_only_defect_lines_not_markdown():
    """3 real defect lines in, preamble and header dropped."""
    rec = _record("d1", "empty", {"critique": CRITIQUE_3, "critique-2": CRITIQUE_1})
    out = arm_delta(rec)
    assert out["defect_lines_initial"] == 3
    assert out["defect_lines_recritique"] == 1
    assert out["delta"] == -2  # negative = the revise turn removed defects


def test_arm_without_recritique_is_not_measured():
    """A --revise-rounds 1 arm has no critique-2. It must be skipped, not scored as 0."""
    rec = _record("d1", "empty", {"critique": CRITIQUE_3})
    assert arm_delta(rec) is None


def test_run_totals_and_direction(tmp_path):
    d = _run_dir(tmp_path, [
        _record("d1", "empty", {"critique": CRITIQUE_3, "critique-2": CRITIQUE_1}),   # improved
        _record("d1", "warmed", {"critique": CRITIQUE_1, "critique-2": CRITIQUE_3}),  # worsened
        _record("d2", "empty", {"critique": CRITIQUE_1, "critique-2": CRITIQUE_1}),   # unchanged
        _record("d2", "warmed", {"critique": CRITIQUE_3}),                            # skipped
    ])
    out = analyse_run(d)

    assert out["arms_measured"] == 3
    assert len(out["arms_without_recritique"]) == 1
    t = out["totals"]
    assert t["improved"] == 1 and t["worsened"] == 1 and t["unchanged"] == 1
    assert t["defect_lines_initial"] == 3 + 1 + 1
    assert t["defect_lines_recritique"] == 1 + 3 + 1
    # Provenance travels with the measurement, same as every other results file here.
    assert out["source_fingerprint"]["memory_py_sha"] == "b44efec3"
    assert out["source_fingerprint"]["revise_rounds"] == 2


def test_the_instrument_names_itself(tmp_path):
    """The output must say which instrument produced it. Reporting these counts as
    results.json's `defect_count` would repeat the _split_claims error: two different
    measurements presented as one."""
    d = _run_dir(tmp_path, [_record("d1", "empty", {"critique": CRITIQUE_3, "critique-2": CRITIQUE_1})])
    out = analyse_run(d)
    assert "material_defects" in out["instrument"]
    assert "NOT judge.count_defects" in out["instrument"]


def test_empty_transcripts_dir_is_an_error(tmp_path):
    d = tmp_path / "run"
    (d / "transcripts").mkdir(parents=True)
    with pytest.raises(SystemExit):
        analyse_run(d)
