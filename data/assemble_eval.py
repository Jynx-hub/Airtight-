"""Assemble a real M4 eval-root from pulled disclosures + distilled loopholes.

Splits the distilled real PTAB loopholes into a warming corpus and a disjoint
held-out checklist, and lays out the three dirs agent/eval/harness.py expects:
  <out>/fixtures/disclosures/   real pulled Disclosures
  <out>/corpus/loopholes/       warming set (real distilled loopholes)
  <out>/groundtruth/checklists/ <disc_id>.json = held-out loopholes (disjoint)

    python -m data.assemble_eval --disclosures 3 --holdout 6 --out data/real-eval
"""

import argparse
import json
import shutil
from pathlib import Path

from airtight import Disclosure, LoopholeRecord


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--loopholes", type=Path, default=Path("data/real/loopholes"))
    ap.add_argument("--disc-src", type=Path, default=Path("data/real/disclosures"))
    ap.add_argument("--out", type=Path, default=Path("data/real-eval"))
    ap.add_argument("--disclosures", type=int, default=3, help="how many disclosures to eval on")
    ap.add_argument("--holdout", type=int, default=6, help="loopholes held out as the checklist")
    args = ap.parse_args()

    loops = sorted(
        (LoopholeRecord.model_validate_json(p.read_text()) for p in args.loopholes.glob("*.json")),
        key=lambda r: r.id,
    )
    if len(loops) < args.holdout + 4:
        print(f"only {len(loops)} loopholes — need more; distill first")
        return 2

    # Deterministic split: last `holdout` are the disjoint checklist, rest warm.
    warming, checklist = loops[: -args.holdout], loops[-args.holdout :]

    # Prefer disclosures with the most substance (longest details).
    discs = sorted(
        (Disclosure.model_validate_json(p.read_text()) for p in args.disc_src.glob("*.json")),
        key=lambda d: len(d.details) + len(d.summary),
        reverse=True,
    )[: args.disclosures]

    if args.out.exists():
        shutil.rmtree(args.out)
    (args.out / "fixtures" / "disclosures").mkdir(parents=True)
    (args.out / "corpus" / "loopholes").mkdir(parents=True)
    (args.out / "groundtruth" / "checklists").mkdir(parents=True)

    for d in discs:
        (args.out / "fixtures" / "disclosures" / f"{d.id}.json").write_text(d.model_dump_json(indent=2))
        # same held-out checklist per disclosure (the real §103/§112 patterns to close)
        (args.out / "groundtruth" / "checklists" / f"{d.id}.json").write_text(
            json.dumps([r.model_dump() for r in checklist], indent=2)
        )
    for r in warming:
        (args.out / "corpus" / "loopholes" / f"{r.id}.json").write_text(r.model_dump_json(indent=2))

    print(f"eval root: {args.out}")
    print(f"  disclosures: {len(discs)}  ({', '.join(d.id for d in discs)})")
    print(f"  warming loopholes: {len(warming)}")
    print(f"  held-out checklist: {len(checklist)}  ({', '.join(r.id for r in checklist)})")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
