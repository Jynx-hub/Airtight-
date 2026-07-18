#!/usr/bin/env bash
# Airtight runtime — the on-box vLLM serve command (HOST-AGNOSTIC).
# Serves ONE OpenAI-compatible model on :8000 — the single pinned `inference.local`
# hop the whole system routes to. This is the SAME `vllm serve` invocation that
# runtime/modal_app.py runs on Modal's free tier (our primary host); it also works
# as-is on any rented GPU box (Vast/RunPod/etc.) if you ever need one — just run it
# there. Keep this file and modal_app.py in sync: one source of truth for the flags.
#
# GUARANTEED path is Nano on ONE GPU (fits VRAM). Bring up Super only if the box is
# big enough. Flags from the vLLM Nemotron 3 cookbooks + HF model cards (verified
# 2026-07-17). NOTE: Nano and Super use DIFFERENT reasoning parsers (nano_v3 vs
# nemotron_v3) — the case block sets the right one per profile.
set -euo pipefail
cd "$(dirname "$0")"
# HF_TOKEN etc. Loads .env WITHOUT clobbering the environment, so "already exported"
# actually wins — a bare `set -a; . ./.env` overwrote exports and made that claim false.
# Matches python-dotenv's default in inference_local.py.
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    key="${line%%=*}"; val="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key-}" ]] || export "$key=$val"
  done < .env
fi

PROFILE="${SERVE_PROFILE:-nano-1xh100}"
SERVED_NAME="${INFERENCE_MODEL:-nemotron}"               # backend-agnostic alias the client pins to
: "${HF_TOKEN:?Set HF_TOKEN (accept the Nemotron license on the HF model page first)}"
export HF_TOKEN

EXTRA=()
case "$PROFILE" in
  nano-1xh100)      # GUARANTEED: Nemotron 3 Nano, single GPU (≥64GB, e.g. 1×H100)
    CKPT=nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16;  TP=1; MAXLEN=262144; REASON=nano_v3
    EXTRA+=(--reasoning-parser-plugin nano_v3_reasoning_parser.py --max-num-seqs 8) ;;
  super-8xh100)     # Nemotron 3 Super BF16, full quality + 256k ctx (only if VRAM/credits allow)
    CKPT=nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16; TP=8; MAXLEN=262144; REASON=nemotron_v3
    EXTRA+=(--enable-expert-parallel) ;;
  super-fp8-4xh100) # Nemotron 3 Super FP8, middle ground (cap context)
    CKPT=nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-FP8;  TP=4; MAXLEN=32768;  REASON=nemotron_v3
    EXTRA+=(--enable-expert-parallel) ;;
  nvfp4-blackwell)  # Nemotron 3 Super NVFP4 — Blackwell (B200/GB10) ONLY, won't run on H100
    CKPT=nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-NVFP4; TP=2; MAXLEN=131072; REASON=super_v3
    EXTRA+=(--enable-expert-parallel --reasoning-parser-plugin super_v3_reasoning_parser.py) ;;
  *) echo "Unknown SERVE_PROFILE=$PROFILE (nano-1xh100 | super-8xh100 | super-fp8-4xh100 | nvfp4-blackwell)"; exit 1 ;;
esac

command -v vllm >/dev/null || pip install -U "vllm>=0.18.1"

echo "▶ Serving $CKPT  (profile=$PROFILE, TP=$TP, max-len=$MAXLEN) as '$SERVED_NAME' on :8000"
exec vllm serve "$CKPT" \
  --served-model-name "$SERVED_NAME" \
  --host 0.0.0.0 --port 8000 \
  --tensor-parallel-size "$TP" \
  --max-model-len "$MAXLEN" \
  --kv-cache-dtype fp8 \
  --mamba-ssm-cache-dtype float32 \
  --enable-chunked-prefill \
  --gpu-memory-utilization 0.9 \
  --trust-remote-code \
  --reasoning-parser "$REASON" \
  --enable-auto-tool-choice \
  --tool-call-parser qwen3_coder \
  "${EXTRA[@]}"
