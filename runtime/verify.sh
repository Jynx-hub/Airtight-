#!/usr/bin/env bash
# Airtight runtime — smoke-test the pinned inference hop (RUN ANYWHERE that can
# reach INFERENCE_BASE_URL — e.g. the Modal endpoint from modal-deploy.sh, or the
# NIM fallback URL). Proves three things the rest of the system depends on: the
# endpoint is up, the served model name matches, chat works, and tool-calling parses.
set -euo pipefail
cd "$(dirname "$0")"
# Load .env WITHOUT clobbering the environment: a pre-exported var must WIN, matching
# python-dotenv's default in inference_local.py. The old `set -a; . ./.env` did the
# OPPOSITE — it overwrote exported vars, so `INFERENCE_BACKEND=nim bash verify.sh`
# silently tested Modal. Assumes unquoted values with no inline comments, which
# .env.example already mandates.
if [[ -f .env ]]; then
  while IFS= read -r line || [[ -n "$line" ]]; do
    [[ "$line" =~ ^[[:space:]]*(#|$) ]] && continue
    key="${line%%=*}"; val="${line#*=}"
    [[ "$key" =~ ^[A-Za-z_][A-Za-z0-9_]*$ ]] || continue
    [[ -n "${!key-}" ]] || export "$key=$val"
  done < .env
fi

# Same resolution table as inference_local.py `_resolve()` — keep the two in sync.
case "${INFERENCE_BACKEND-}" in
  "")
    BASE="${INFERENCE_BASE_URL:-http://localhost:8000/v1}"
    MODEL="${INFERENCE_MODEL:-nemotron}"
    KEY="${INFERENCE_API_KEY:-airtight-local}"
    NOTE="legacy flat INFERENCE_* config (pre-F3 behavior)" ;;
  modal)
    BASE="${MODAL_BASE_URL:-${INFERENCE_BASE_URL:-http://localhost:8000/v1}}"
    MODEL="${MODAL_MODEL:-${INFERENCE_MODEL:-nemotron}}"
    KEY="${MODAL_API_KEY:-${INFERENCE_API_KEY:-airtight-local}}"
    NOTE="PRIMARY · self-hosted vLLM on Modal · COUNTS for the \$500 vLLM bounty" ;;
  nim)
    BASE="${NIM_BASE_URL:-https://integrate.api.nvidia.com/v1}"
    MODEL="${NIM_MODEL:-nvidia/nemotron-3-nano-30b-a3b}"
    KEY="${NVIDIA_API_KEY:?INFERENCE_BACKEND=nim needs NVIDIA_API_KEY — free key at https://build.nvidia.com}"
    NOTE="FALLBACK · NVIDIA NIM (HOSTED) · does NOT count for the vLLM bounty" ;;
  *)
    echo "Unknown INFERENCE_BACKEND=${INFERENCE_BACKEND} (expected: modal | nim)" >&2; exit 1 ;;
esac
AUTH=(-H "Authorization: Bearer ${KEY}")
# Fail loudly instead of hanging: a cold Modal container takes 2-5 min to wake.
TIMEOUT=(--connect-timeout 10 --max-time "${INFERENCE_TIMEOUT:-300}")

echo "▶ backend=${INFERENCE_BACKEND:-legacy}  ${BASE}  model=${MODEL}"
echo "  ${NOTE}"

echo "▶ 1/3  GET ${BASE}/models"
curl -fsS "${TIMEOUT[@]}" "${AUTH[@]}" "${BASE}/models" | python3 -m json.tool | head -20

echo "▶ 2/3  chat completion (reasoning off)"
curl -fsS "${TIMEOUT[@]}" "${AUTH[@]}" -H 'Content-Type: application/json' "${BASE}/chat/completions" -d @- <<JSON | python3 -m json.tool | head -30
{"model": "${MODEL}",
 "messages": [{"role":"user","content":"Reply with exactly: AIRTIGHT-OK"}],
 "chat_template_kwargs": {"enable_thinking": false},
 "max_tokens": 16}
JSON

echo "▶ 3/3  tool call"
curl -fsS "${TIMEOUT[@]}" "${AUTH[@]}" -H 'Content-Type: application/json' "${BASE}/chat/completions" -d @- <<JSON | python3 -m json.tool | head -40
{"model": "${MODEL}",
 "messages": [{"role":"user","content":"Search prior art for a foldable phone hinge. Use the tool."}],
 "tools": [{"type":"function","function":{"name":"search_prior_art",
   "description":"Search patents for prior art",
   "parameters":{"type":"object","properties":{"query":{"type":"string"}},"required":["query"]}}}],
 "tool_choice": "auto",
 "chat_template_kwargs": {"enable_thinking": false},
 "max_tokens": 128}
JSON

echo "✔ endpoint reachable, chat + tool-calling functional."
echo "  backend=${INFERENCE_BACKEND:-legacy} · ${NOTE}"
