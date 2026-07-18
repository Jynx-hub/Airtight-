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
CHART=$(ls -dt results/ablation/2026*/chart.html 2>/dev/null | head -1 || true)
if [ -n "${CHART:-}" ]; then
  $PY - "$CHART" <<'EOF'
import json, sys, pathlib
d = pathlib.Path(sys.argv[1]).parent
p = json.load(open(d/"results.json"))
res = p["results"]
def avg(c,k): xs=[r[k] for r in res if r["condition"]==c]; return sum(xs)/len(xs)
wins = sum(1 for pr in p["pairs"] if pr["loopholes_caught_delta"]>0)
print(f"    {p['disclosures_completed']} disclosures, warmed on {p['corpus_size']} real loopholes ({p['fingerprint']['mode']})")
print(f"    loopholes caught: empty {avg('empty','loopholes_caught'):.2f} -> warmed {avg('warmed','loopholes_caught'):.2f}  (warmed wins {wins}/{len(p['pairs'])})")
print(f"    chart: {sys.argv[1]}")
EOF
else
  echo "    (no ablation chart yet — run: AIRTIGHT_MODE=live ... python -m agent.eval --data-root data/real-eval --fast)"
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
