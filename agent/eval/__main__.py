"""CLI for the M4 ablation.

    python -m agent.eval --data-root data --k 5 --runs 1

Stub mode exercises all plumbing (delta = 0 by construction); set
AIRTIGHT_MODE=live for the real ablation.
"""

import argparse
import json
from pathlib import Path

from agent.eval.harness import run_ablation


def main() -> None:
    ap = argparse.ArgumentParser(description="Run the empty-vs-warmed ablation.")
    ap.add_argument("--data-root", type=Path, default=Path("data"))
    ap.add_argument("--k", type=int, default=5)
    ap.add_argument("--runs", type=int, default=1)
    ap.add_argument("--out", type=Path, default=Path("results/ablation"))
    args = ap.parse_args()

    results_path = run_ablation(args.data_root, k=args.k, runs=args.runs, out_root=args.out)
    payload = json.loads(results_path.read_text())

    print(f"results:  {results_path}")
    print(f"chart:    {results_path.parent / 'chart.html'}")
    print(f"mode:     {payload['fingerprint']['mode']}")
    for pair in payload["pairs"]:
        print(
            f"  {pair['disclosure_id']}: loopholes {pair['loopholes_caught_delta']:+d}, "
            f"time {pair['drafting_seconds_delta']:+.1f}s, defects {pair['defect_count_delta']:+d}"
        )


if __name__ == "__main__":
    main()
