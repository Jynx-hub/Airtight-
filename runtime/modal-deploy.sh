#!/usr/bin/env bash
# Airtight runtime — deploy the vLLM/Nemotron server to Modal's FREE tier.
# Replaces the retired Brev provisioning flow. RUN ON YOUR LAPTOP. See runtime/README.md.
#
# One-time prep:
#   1) pip install modal && modal token new          # free account, no card
#   2) Accept the NVIDIA Open Model License on the Nemotron 3 Nano HF model page.
#   3) modal secret create huggingface HF_TOKEN=hf_xxx   # gated-weights pull token
#
# Cost: scale-to-zero → you only burn the free monthly credit while a request runs.
# Default GPU profile is L40S + FP8 (cheapest fit). For the A100-80GB BF16 quality
# path:  MODAL_GPU_PROFILE=a100-bf16 bash runtime/modal-deploy.sh
set -euo pipefail
cd "$(dirname "$0")"
# Load .env WITHOUT clobbering the environment: a pre-exported var must WIN, matching
# python-dotenv's default in inference_local.py. A bare `set -a; . ./.env` did the
# OPPOSITE, which silently broke this script's own documented usage above
# (`MODAL_GPU_PROFILE=a100-bf16 bash modal-deploy.sh`) and the demo keep-warm flow
# (`MODAL_MIN_CONTAINERS=1 bash modal-deploy.sh` deployed scale-to-zero anyway).
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    key="${line%%=*}"; val="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key-}" ]] || export "$key=$val"
  done < .env
fi

command -v modal >/dev/null || { echo "modal CLI not found — pip install modal && modal token new"; exit 1; }

# Optional one-time weight pre-warm: download the ~30GB into the Modal Volume BEFORE
# the demo so the first real request never eats a cold download. Uncomment to run:
#   modal run modal_app.py::prewarm    # (add a prewarm fn if you want this)

echo "▶ Deploying airtight-nemotron to Modal (profile=${MODAL_GPU_PROFILE:-l40s-fp8})…"
modal deploy modal_app.py

cat <<'EOF'

✔ Deployed. Next:
  1) Copy the web-endpoint URL Modal printed (…serve.modal.run) and set in runtime/.env:
       INFERENCE_BASE_URL=https://<workspace>--airtight-nemotron-serve.modal.run/v1
       INFERENCE_MODEL=nemotron
       INFERENCE_API_KEY=airtight-local
  2) Smoke test:            bash verify.sh
  3) Doorway test:          python inference_local.py        # expect AIRTIGHT-OK
  4) Keep warm for demo:    MODAL_MIN_CONTAINERS=1 bash modal-deploy.sh
  5) Stop billing after:    MODAL_MIN_CONTAINERS=0 bash modal-deploy.sh
     (scale-to-zero is automatic 5 min after the last request; step 4/5 only pin a
      warm replica for the judged run. Go through this script rather than bare
      `modal deploy` — it cd's correctly and loads .env non-destructively, so the
      inline var actually wins.)
  Fallback to the free NIM endpoint any time:  bash serve-nim.sh
  Demo-day card + consumer quickstart:         RUNBOOK.md
EOF
