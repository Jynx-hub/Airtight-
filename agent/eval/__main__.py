"""CLI for the M4 ablation.

    python -m agent.eval --data-root data --k 5 --runs 1
    python -m agent.eval --data-root data --fast   # reasoning-off + capped drafts (quick)
    python -m agent.eval --data-root data/real --layout pooled --n 10   # real USPTO pull

Stub mode exercises all plumbing (delta = 0 by construction); set
AIRTIGHT_MODE=live for the real ablation.
"""

import argparse
import json
import time
from pathlib import Path

from agent.eval.harness import DRAFT_GEN, FAST_DRAFT_GEN, SPLIT_SEED, run_ablation


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the empty-vs-warmed ablation.")
    ap.add_argument("--data-root", type=Path, default=Path("data"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("results/ablation"))
    ap.add_argument("--fast", action="store_true",
                    help="reasoning-off + capped drafts — quicker, shallower (same setting both arms)")
    ap.add_argument("--deadline-min", type=float, default=None,
                    help="stop cleanly after N minutes (finalizes a partial chart) — "
                         "keeps a windowed run from firing calls past the GPU window")
    ap.add_argument("--layout", choices=("fixtures", "pooled"), default="fixtures",
                    help="'fixtures' = the pre-split curated tree; 'pooled' = one pool split here")
    ap.add_argument("--n", type=int, default=None,
                    help="graded disclosures (pooled: holdout size; fixtures: cap). Bounds a metered run.")
    ap.add_argument("--seed", type=int, default=SPLIT_SEED,
                    help="holdout selection seed — same (seed, n) picks the same disclosures")
    args = ap.parse_args()

    draft_gen = FAST_DRAFT_GEN if args.fast else DRAFT_GEN
    deadline = time.time() + args.deadline_min * 60 if args.deadline_min else None
    results_path = run_ablation(args.data_root, k=args.k, runs=args.runs, out_root=args.out,
                                draft_gen=draft_gen, layout=args.layout, n=args.n, seed=args.seed,
                                deadline=deadline)
    payload = json.loads(results_path.read_text())

    print(f"results:  {results_path}")
    print(f"chart:    {results_path.parent / 'chart.html'}")
    print(f"mode:     {payload['fingerprint']['mode']}")
    split = payload["fingerprint"].get("split")
    if split:
        print(f"split:    {split['n']} held out of {split['paired']} paired "
              f"({len(split['unpaired_disclosure_ids'])} unpaired, skipped) · "
              f"{split['graded_records']} graded records vs {split['corpus_records']} warming · "
              f"seed {split['seed']}")
    for pair in payload["pairs"]:
        print(
            f"  {pair['disclosure_id']}: loopholes {pair['loopholes_caught_delta']:+d}, "
            f"time {pair['drafting_seconds_delta']:+.1f}s, defects {pair['defect_count_delta']:+d}"
        )


if __name__ == "__main__":
    main()
