"""Re-score banked ablation drafts without re-drafting them.

Why this exists: `_split_claims` decided how much of each draft the judge saw, and
it decided differently per arm depending on markdown (see the fix commit and
`docs/WORKSTREAMS.md`). Every number scored through the old parser is void — but
the *drafts* are not. `_split_claims` is called once, at the end of
`loop.draft_patent`, purely to populate `Draft.claims`; no model turn ever reads
its output. So the banked replies are exactly what the model produced, and the
honest repair is to re-score them rather than pay to generate them again.

That also makes this a STRONGER comparison than a fresh run: the drafts are held
fixed while the one known-broken variable is corrected.

Cost shape: re-scoring is ~2 sequential round-trips per arm (score_checklist fans
its per-item calls out concurrently, then one defect call), versus the 4 drafting
turns plus scoring that a full run pays.

    python -m agent.eval.rejudge --run results/ablation/20260718-183817

Validate against the free mock first — `python runtime/mock_endpoint.py --port 8001`
— exactly as a full run should be.
"""

from __future__ import annotations

import argparse
import json
import subprocess
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from airtight import EvalResult, config

from . import judge
from .chart import write_chart
from .harness import _pair_deltas, load_checklist
from ..loop import _split_claims


def _git_sha() -> str:
    """Captured at run START.

    The full harness stamps this when it writes results.json, so a commit landing
    on any branch mid-run silently rewrites the run's provenance — which is how
    `20260718-183817` came to claim a SHA that post-dates the code it ran.
    """
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True,
            cwd=Path(__file__).parent,
        ).stdout.strip()
    except OSError:
        return "unknown"


def final_reply(record: dict) -> str | None:
    """The post-revision draft — the same text `draft_patent` passed to `Draft`.

    Walk backwards to the last turn carrying a reply, because how many revise
    rounds fired varies per arm.
    """
    for turn in reversed(record.get("transcript") or []):
        if isinstance(turn, dict) and turn.get("reply"):
            return turn["reply"]
    return None


def rejudge_run(run_dir: Path, data_root: Path, out_root: Path) -> Path:
    run_dir = Path(run_dir)
    started_sha = _git_sha()  # BEFORE any model call, see _git_sha
    source = json.loads((run_dir / "results.json").read_text())

    records = []
    for path in sorted((run_dir / "transcripts").glob("*.json")):
        record = json.loads(path.read_text())
        reply = final_reply(record)
        if reply is None:
            print(f"  skip {path.name}: no reply banked")
            continue
        records.append((record, reply))

    # Pair ordering is load-bearing: _pair_deltas buckets by (disclosure_id, i//2),
    # so each disclosure's empty must sit immediately before its warmed.
    by_disclosure: dict[str, dict] = {}
    for record, reply in records:
        by_disclosure.setdefault(record["disclosure_id"], {})[record["condition"]] = (record, reply)

    results: list[EvalResult] = []
    rescored = []
    for disclosure_id, arms in sorted(by_disclosure.items()):
        if not {"empty", "warmed"} <= arms.keys():
            print(f"  skip {disclosure_id}: unpaired ({sorted(arms)})")
            continue
        checklist = load_checklist(data_root / "checklists", disclosure_id)
        for condition in ("empty", "warmed"):
            record, reply = arms[condition]
            claims = _split_claims(reply)
            claims_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(claims))

            verdicts = judge.score_checklist(claims_text, checklist)
            defects = judge.count_defects(claims_text, reply)

            old = record["result"]
            results.append(EvalResult(
                disclosure_id=disclosure_id,
                condition=condition,
                loopholes_caught=sum(v.closed for v in verdicts),
                checklist_size=len(checklist),
                # Carried from the source run — nothing was re-drafted here, so
                # reporting a fresh number would be inventing a measurement.
                drafting_seconds=old["drafting_seconds"],
                defect_count=len(defects),
            ))
            rescored.append({
                "disclosure_id": disclosure_id,
                "condition": condition,
                "claims_parsed": len(claims),
                "judged_chars": len(claims_text),
                "old_loopholes_caught": old["loopholes_caught"],
                "new_loopholes_caught": results[-1].loopholes_caught,
            })
            print(f"  {disclosure_id:22s} {condition:7s} claims={len(claims):3d} "
                  f"judged={len(claims_text):6d}ch  caught {old['loopholes_caught']} -> "
                  f"{results[-1].loopholes_caught}")

    # The asymmetry that voided the source run, measured here so the repair is
    # evidenced rather than asserted.
    asymmetry = []
    for disclosure_id in sorted(by_disclosure):
        arm = {r["condition"]: r for r in rescored if r["disclosure_id"] == disclosure_id}
        if {"empty", "warmed"} <= arm.keys():
            e, w = arm["empty"]["judged_chars"], arm["warmed"]["judged_chars"]
            asymmetry.append({
                "disclosure_id": disclosure_id,
                "empty_judged_chars": e,
                "warmed_judged_chars": w,
                "ratio": round(max(e, w) / max(min(e, w), 1), 2),
            })

    out_dir = Path(out_root) / datetime.now().strftime("%Y%m%d-%H%M%S")
    out_dir.mkdir(parents=True)
    payload = {
        "fingerprint": {
            "kind": "rejudge",  # NOT a fresh ablation — drafts were reused
            "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
            "mode": config.MODE,
            "model": config.MODEL,
            "base_url_host": urlparse(config.BASE_URL).hostname or "(none)",
            "judge_gen": judge.JUDGE_GEN,
            # Carried from the source run: the drafts were produced under these, and
            # write_chart reads them. Restating them is honest — nothing re-drafted.
            "k": source.get("fingerprint", {}).get("k"),
            "runs": source.get("fingerprint", {}).get("runs"),
            "draft_gen": source.get("fingerprint", {}).get("draft_gen"),
            "git_sha": started_sha,
            "git_sha_captured": "run-start",
            "source_run": str(run_dir),
            "source_git_sha": source.get("fingerprint", {}).get("git_sha"),
            # Carried so `docs/GPU-RERUN-RUNBOOK.md` step 5 can verify a re-judge the
            # same way it verifies a fresh run. Null for runs that predate b2d395e —
            # which is honest: those cannot prove which ranker produced their drafts.
            # Re-judging performs no retrieval, so the ranker that matters is the
            # SOURCE run's, never this process's.
            "source_memory_py_sha": source.get("fingerprint", {}).get("memory_py_sha"),
            "source_draft_gen": source.get("fingerprint", {}).get("draft_gen"),
            "source_split": source.get("fingerprint", {}).get("split"),
            "drafts_regenerated": False,
        },
        "corpus_size": source.get("corpus_size"),
        "results": [r.model_dump() for r in results],
        "pairs": _pair_deltas(results),
        "scoring_asymmetry": asymmetry,
        "rescored": rescored,
        "disclosures_completed": len(results) // 2,
    }
    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    write_chart(results_path, out_dir / "chart.html")
    return results_path


def main() -> None:
    ap = argparse.ArgumentParser(description="Re-score banked ablation drafts with the current parser.")
    ap.add_argument("--run", type=Path, required=True, help="source run dir (with transcripts/)")
    ap.add_argument("--data-root", type=Path, default=Path("data/real"))
    ap.add_argument("--out", type=Path, default=Path("results/rejudge"))
    args = ap.parse_args()

    path = rejudge_run(args.run, args.data_root, args.out)
    payload = json.loads(path.read_text())

    wins = sum(p["loopholes_caught_delta"] > 0 for p in payload["pairs"])
    losses = sum(p["loopholes_caught_delta"] < 0 for p in payload["pairs"])
    ties = sum(p["loopholes_caught_delta"] == 0 for p in payload["pairs"])
    worst = max((a["ratio"] for a in payload["scoring_asymmetry"]), default=0)

    print(f"\nresults:  {path}")
    print(f"mode:     {payload['fingerprint']['mode']} · source {payload['fingerprint']['source_run']}")
    print(f"warmed:   {wins} wins / {losses} losses / {ties} ties  (of {len(payload['pairs'])})")
    print(f"worst scoring asymmetry after repair: {worst}x  (source run peaked at 13.2x)")


if __name__ == "__main__":
    main()
