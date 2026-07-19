"""Measure whether the loop's revise turn actually sharpens a draft, from banked transcripts.

Why this exists: the cross-run ablation (empty vs warmed memory) came back negative, and
it can only ever answer "does memory carry across runs". It cannot answer the *other*
recursion claim — that a single run improves itself. That claim lives inside one run, in
the gap between the first critique and the re-critique of the revised draft.

At `--revise-rounds 1` the answer is structurally unavailable: `loop.py` skips the
re-critique after the last permitted revise, so the run never looks at its own repair. A
`--revise-rounds 2` run banks both `critique` and `critique-2`, and this module reads them
off disk. **No model calls, no GPU** — the drafts and critiques already exist.

    python -m agent.eval.revise_delta --run results/ablation/20260718-201500

⚠️ On what this measures. `material_defects` counts critique lines that name a statute or a
defect keyword. That is NOT the same instrument as `judge.count_defects`, which requires
verbatim-grounded quotes and caps at 6, and which is what `defect_count` in `results.json`
reports. Do not present a number from here as commensurable with that one. The honest
phrasing is "critique lines naming a defect fell from X to Y after the revise turn".
Reporting it as a drop in judged defects would repeat the `_split_claims` class of error:
two different measurements presented as one.
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path

from agent.episodes import material_defects

INITIAL, RECRITIQUE = "critique", "critique-2"


def _reply(record: dict, turn_name: str) -> str | None:
    """The reply for a named turn, or None if that turn never fired."""
    for turn in record.get("transcript") or []:
        if isinstance(turn, dict) and turn.get("turn") == turn_name and turn.get("reply"):
            return turn["reply"]
    return None


def arm_delta(record: dict) -> dict | None:
    """One transcript → before/after defect-line counts, or None if it has no re-critique."""
    before, after = _reply(record, INITIAL), _reply(record, RECRITIQUE)
    if before is None or after is None:
        return None
    b, a = material_defects(before), material_defects(after)
    return {
        "disclosure_id": record.get("disclosure_id"),
        "condition": record.get("condition"),
        "defect_lines_initial": len(b),
        "defect_lines_recritique": len(a),
        "delta": len(a) - len(b),
        # Kept so a reviewer can read what was actually counted rather than trusting a
        # bare integer — the same reason rejudge emits per-pair scoring_asymmetry.
        "initial_lines": b,
        "recritique_lines": a,
    }


def analyse_run(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    transcripts = sorted((run_dir / "transcripts").glob("*.json"))
    if not transcripts:
        raise SystemExit(f"no transcripts under {run_dir}/transcripts/")

    arms, skipped = [], []
    for path in transcripts:
        record = json.loads(path.read_text())
        delta = arm_delta(record)
        (arms.append(delta) if delta else skipped.append(path.name))

    source_fp = {}
    results_path = run_dir / "results.json"
    if results_path.exists():
        source_fp = json.loads(results_path.read_text()).get("fingerprint", {})

    improved = sum(a["delta"] < 0 for a in arms)
    worsened = sum(a["delta"] > 0 for a in arms)
    return {
        "source_run": str(run_dir),
        "source_fingerprint": {
            "git_sha": source_fp.get("git_sha"),
            "memory_py_sha": source_fp.get("memory_py_sha"),
            "revise_rounds": source_fp.get("revise_rounds"),
            "mode": source_fp.get("mode"),
        },
        "instrument": "agent.episodes.material_defects — critique lines naming a statute or "
                      "defect keyword. NOT judge.count_defects; not comparable to results.json "
                      "defect_count.",
        "arms_measured": len(arms),
        "arms_without_recritique": skipped,
        "totals": {
            "defect_lines_initial": sum(a["defect_lines_initial"] for a in arms),
            "defect_lines_recritique": sum(a["defect_lines_recritique"] for a in arms),
            "improved": improved,
            "worsened": worsened,
            "unchanged": len(arms) - improved - worsened,
        },
        "arms": arms,
    }


def main() -> None:
    ap = argparse.ArgumentParser(
        description="Within-run defect reduction from banked --revise-rounds 2 transcripts.")
    ap.add_argument("--run", type=Path, required=True, help="run dir (with transcripts/)")
    ap.add_argument("--out", type=Path, default=None,
                    help="write JSON here (default: <run>/revise_delta.json)")
    args = ap.parse_args()

    payload = analyse_run(args.run)
    out = args.out or args.run / "revise_delta.json"
    out.write_text(json.dumps(payload, indent=2))

    t, fp = payload["totals"], payload["source_fingerprint"]
    print(f"\nsource:   {payload['source_run']}  (revise_rounds={fp.get('revise_rounds')}, "
          f"mode={fp.get('mode')})")
    print(f"ranker:   memory_py_sha={fp.get('memory_py_sha')}")
    if not payload["arms_measured"]:
        # The overwhelmingly likely cause, so say it rather than printing zeros.
        raise SystemExit(
            "\nNo arm has a re-critique turn. At --revise-rounds 1 the loop skips it after the\n"
            "last revise, so this measurement needs a --revise-rounds 2 run. Nothing to report.")
    if payload["arms_without_recritique"]:
        print(f"skipped:  {len(payload['arms_without_recritique'])} arm(s) with no re-critique "
              "(the revise loop exited early — no material defects to fix)")
    print(f"arms:     {payload['arms_measured']} measured")
    print(f"defect lines: {t['defect_lines_initial']} initial -> {t['defect_lines_recritique']} "
          f"after revise")
    print(f"per arm:  {t['improved']} improved / {t['worsened']} worsened / {t['unchanged']} unchanged")
    print(f"\nwrote {out}")
    print("Report as critique lines, not as judged defects — see this module's docstring.")


if __name__ == "__main__":
    main()
