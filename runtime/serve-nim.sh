#!/usr/bin/env bash
# Airtight runtime — FALLBACK: the free NVIDIA NIM hosted dev endpoint.
#
# This is NOT a server you run — it's a HOSTED OpenAI-compatible endpoint. Falling
# back to it is a ONE-VAR FLIP (`INFERENCE_BACKEND=nim`); the doorway
# (inference_local.py) needs nothing else, and your Modal credentials survive it.
#
# This script does not just PRINT the flip — it PROVES it, by running verify.sh
# against NIM in a subshell. It never writes .env, and it checks its own claim: the
# file is fingerprinted before and after, so a stray write fails the run loudly.
# That matters while the Lane A load test (F2) is measuring the Modal endpoint —
# those throughput numbers are the $500 bounty evidence and must not be perturbed.
#
# Note: a hosted API does NOT count toward the $500 vLLM bounty (that needs the
# self-hosted Modal vLLM path). This is purely the safety net — same role it always
# had. Get a free `nvapi-...` key at https://build.nvidia.com (no card).
set -euo pipefail
cd "$(dirname "$0")"

# Load .env WITHOUT clobbering the environment: a pre-exported var must WIN, matching
# python-dotenv's default in inference_local.py. A bare `set -a; . ./.env` does the
# OPPOSITE — it overwrites exported vars, which would make the flip below a no-op.
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    key="${line%%=*}"; val="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key-}" ]] || export "$key=$val"
  done < .env
fi

if [[ -z "${NVIDIA_API_KEY:-}" ]]; then
  cat <<'EOF' >&2
✘ NVIDIA_API_KEY is empty — there is nothing to fall back to yet.

  1. Go to https://build.nvidia.com and hit "Get API Key" (free, no card).
  2. Put it in runtime/.env:   NVIDIA_API_KEY=nvapi-xxxxxxxx
  3. Re-run:                   bash serve-nim.sh
EOF
  exit 1
fi

ENV_SHA_BEFORE=$(shasum -a 256 .env | awk '{print $1}')

echo "▶ Proving the fallback flip:  INFERENCE_BACKEND=nim bash verify.sh"
echo
( export INFERENCE_BACKEND=nim; bash verify.sh )

ENV_SHA_AFTER=$(shasum -a 256 .env | awk '{print $1}')
if [[ "$ENV_SHA_BEFORE" != "$ENV_SHA_AFTER" ]]; then
  echo "✘ runtime/.env CHANGED during this run — it must not. Tell whoever is running" >&2
  echo "  the load test (F2): their numbers may be against the wrong backend." >&2
  exit 1
fi

cat <<'EOF'

✔ NIM fallback proven — and runtime/.env is byte-identical.

  To actually fall back, set ONE var in runtime/.env:   INFERENCE_BACKEND=nim
  To return to the judged path:                         INFERENCE_BACKEND=modal

  Remember: NIM is HOSTED. It keeps the demo alive, but it does not count toward the
  $500 vLLM bounty — only the self-hosted Modal vLLM path does. Flip back before
  taking any bounty measurement.
EOF

# ── Self-host NIM instead? (only if you have your OWN GPU box) ─────────────────
# The line below runs the NIM Turbo container locally — the SAME OpenAI API on :8000,
# auto-selecting the precision profile for the detected GPUs. Needs an NGC key and a
# CUDA GPU; irrelevant to the free hosted endpoint above. Uncomment to use:
#
# : "${NGC_API_KEY:?Set NGC_API_KEY (from ngc.nvidia.com) to pull the NIM image}"
# echo "$NGC_API_KEY" | docker login nvcr.io --username '$oauthtoken' --password-stdin
# LOCAL_NIM_CACHE="${LOCAL_NIM_CACHE:-$HOME/.cache/nim}"
# mkdir -p "$LOCAL_NIM_CACHE" && chmod -R a+w "$LOCAL_NIM_CACHE"
# exec docker run --rm --gpus=all --shm-size=16GB -e NGC_API_KEY \
#   -v "$LOCAL_NIM_CACHE:/opt/nim/.cache" -p 8000:8000 \
#   "${NIM_IMAGE:-nvcr.io/nim/nvidia/nemotron-3-super-120b-a12b-turbo:1.0.0}"
