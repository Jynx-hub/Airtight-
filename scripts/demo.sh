#!/usr/bin/env bash
# Airtight demo driver — the three-beat flow, one command.
# Runs entirely offline (committed chart + rehearsal modes) so it works with no
# GPU and no credentials. Swap the fallbacks noted in docs/DEMO-RUNBOOK.md when
# the live endpoint + HiddenLayer key are available.
set -euo pipefail
cd "$(dirname "$0")/.."
PY=${PY:-.venv/bin/python}

echo "############################################################"
echo "# AIRTIGHT — three beats, one boundary, three tracks"
echo "############################################################"

echo
echo ">>> BEAT 1 — the speed-run (Track 1: recursive intelligence)"
echo "    Same model, same prompts, memory empty vs warmed on real PTAB loopholes."
# Read the REJUDGE run, not whatever ablation chart is newest by mtime. The
# 20260718-183817 ablation scored its two arms on asymmetric targets (up to 13x —
# docs/WORKSTREAMS.md) and must not be quoted; the rejudge re-scores those same banked
# drafts against the fixed _split_claims parser. Picking by mtime silently selects the
# discredited run, which is the one number on disk we least want on a judge's screen.
RUN=$(ls -dt results/rejudge/*/results.json 2>/dev/null | head -1 || true)
if [ -z "${RUN:-}" ]; then
  RUN=$(ls -dt results/ablation/2026*/results.json 2>/dev/null | head -1 || true)
  [ -n "${RUN:-}" ] && echo "    !! no rejudge result — falling back to a raw ablation run; check scoring symmetry before quoting"
fi
if [ -n "${RUN:-}" ]; then
  $PY - "$RUN" <<'EOF'
import json, sys
p = json.load(open(sys.argv[1]))
res, pairs = p["results"], p["pairs"]
tot = lambda c: sum(r["loopholes_caught"] for r in res if r["condition"] == c)
def wlt(prs):
    w = sum(1 for pr in prs if pr["loopholes_caught_delta"] > 0)
    l = sum(1 for pr in prs if pr["loopholes_caught_delta"] < 0)
    return w, l, len(prs) - w - l
fp = p["fingerprint"]
print(f"    {p['disclosures_completed']} disclosures, warmed on {p['corpus_size']} real loopholes"
      f" ({fp['mode']}, {fp.get('kind', 'ablation')})")
print(f"    loopholes caught — empty {tot('empty')} · warmed {tot('warmed')}")
print("    all {} pairs: {} win / {} loss / {} tie".format(len(pairs), *wlt(pairs)))
# Only the pairs where the judge saw comparable text carry any signal at all.
asym = {a["disclosure_id"]: a["ratio"] for a in p.get("scoring_asymmetry", [])}
if asym:
    sym = [pr for pr in pairs if asym.get(pr["disclosure_id"], 99) <= 1.5]
    print("    {} symmetric pairs (<=1.5x judged text): {} win / {} loss / {} tie".format(len(sym), *wlt(sym)))
print("    HONEST READ: warmed does not beat empty under --fast. The learning mechanism is")
print("    real and demos live; the positive delta is the open question. Cause not yet")
print("    isolated — see SUBMISSION.md and docs/RECURSION-EVIDENCE.md.")
print(f"    source: {sys.argv[1]}")
EOF
else
  echo "    (no ablation result yet — run: AIRTIGHT_MODE=live ... python -m agent.eval --data-root data/real)"
fi

echo
echo ">>> BEAT 2 — the poison (Track 2: HiddenLayer, all five hops)"
AIRTIGHT_MODE=stub $PY -m agent.poison_demo --fake

echo
echo ">>> BEAT 3 — the wall (Track 3: OpenShell containment)"
$PY -m containment.demo

echo
echo "############################################################"
echo "# vLLM bounty: 65.2 -> 695.8 tok/s (10.67x) — docs/THROUGHPUT.md"
echo "############################################################"
