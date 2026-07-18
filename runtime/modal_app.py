"""Airtight runtime — serve Nemotron on vLLM via Modal's FREE tier.

This is the PRIMARY inference backend (replaces the retired Brev plan). It stands up
ONE OpenAI-compatible vLLM server for Nemotron 3 Nano and exposes it as a web endpoint
— the single pinned `inference.local` hop the whole system routes through. Both
HiddenLayer (Lane B) and OpenShell (Lane C) enforce on this one URL.

Why Modal: serverless GPU with scale-to-zero. You pay per-second only while a request
is running, so a hackathon fits inside the free monthly credit. It is still SELF-HOSTED
vLLM (continuous batching + the Nano small-model punch), so the $500 vLLM bounty is
fully intact — Modal just replaces the rented box.

The doorway (`inference_local.py`) does NOT change: it reads INFERENCE_BASE_URL /
INFERENCE_MODEL / INFERENCE_API_KEY from operator env. After `modal deploy`, put the
Modal URL (+ `/v1`) into INFERENCE_BASE_URL. To fall back to the free NVIDIA NIM dev
endpoint, flip those three env vars — no code change (see runtime/serve-nim.sh).

Deploy:  bash runtime/modal-deploy.sh   (wraps `modal deploy runtime/modal_app.py`)
Flags mirror runtime/serve-vllm.sh's `nano-1xh100` profile — one source of truth for
the vLLM invocation. See docs/INFERENCE-LOCAL.md and research/vllm.md.
"""
from __future__ import annotations

import os
import subprocess
from pathlib import Path

import modal

MINUTES = 60
VLLM_PORT = 8000
SERVED_NAME = os.environ.get("INFERENCE_MODEL", "nemotron")  # backend-agnostic client alias

# ── GPU / precision profile ───────────────────────────────────────────────────
# Default is the CHEAPEST tier that fits Nano: L40S (48GB) + the FP8 checkpoint
# (Ada natively runs FP8). Swap to the A100-80GB BF16 quality path with ONE env var
# at deploy time: `MODAL_GPU_PROFILE=a100-bf16 modal deploy runtime/modal_app.py`.
# Weights: 30B params ≈ 30GB FP8 / 60GB BF16. Nano's hybrid Mamba arch keeps only 6
# attention layers' KV cache, so long context is cheap on modest headroom.
PROFILES = {
    "l40s-fp8": {
        "gpu": "L40S",
        "checkpoint": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-FP8",
        "max_model_len": 131072,          # 128K fits L40S KV headroom
        "kv_cache_dtype": "fp8",
        "extra_env": {"VLLM_USE_FLASHINFER_MOE_FP8": "1"},  # FP8 MoE kernels (Ada/Hopper)
    },
    "a100-bf16": {
        "gpu": "A100-80GB",
        "checkpoint": "nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16",
        "max_model_len": 262144,          # 256K on 80GB
        "kv_cache_dtype": "auto",         # Ampere has no FP8 tensor cores
        "extra_env": {},
    },
}
_PROFILE_NAME = os.environ.get("MODAL_GPU_PROFILE", "l40s-fp8")
PROFILE = PROFILES[_PROFILE_NAME]
MODEL_REVISION = os.environ.get("MODAL_MODEL_REVISION", "main")  # pin a commit SHA before the demo

# nano_v3 is a PLUGIN reasoning parser per the vLLM Nemotron-3-Nano recipe — the .py
# file is baked into the image below. If your pinned vLLM ships `nano_v3` built-in
# (check `vllm serve --help | grep -i reason`), set this False and drop the plugin file.
USE_REASONING_PLUGIN = True
_PARSER_FILE = Path(__file__).parent / "nano_v3_reasoning_parser.py"

# ── Image: CUDA devel + vLLM + fast HF downloads, with the parser plugin baked in ─
vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    # vLLM 0.12.0 is the recipe-recommended build for Nemotron 3 Nano (0.11.2 min).
    .uv_pip_install("vllm==0.12.0", "huggingface_hub[hf_transfer]")
    # Bake the chosen profile name INTO the image so the container resolves the same
    # PROFILE at runtime. Local deploy-time env vars do NOT reach the container, so
    # without this the container falls back to the default profile (wrong checkpoint).
    .env({"HF_HUB_ENABLE_HF_TRANSFER": "1", "MODAL_GPU_PROFILE": _PROFILE_NAME})
    .add_local_file(str(_PARSER_FILE), "/root/nano_v3_reasoning_parser.py", copy=True)
)

# ── Persistent caches so cold starts don't re-download the ~30GB weights ──────────
hf_cache_vol = modal.Volume.from_name("airtight-hf-cache", create_if_missing=True)
vllm_cache_vol = modal.Volume.from_name("airtight-vllm-cache", create_if_missing=True)

# Gated NVIDIA weights: accept the Open Model License on the HF model page once, then
#   modal secret create huggingface HF_TOKEN=hf_xxx
hf_secret = modal.Secret.from_name("huggingface")

app = modal.App("airtight-nemotron")


@app.function(
    image=vllm_image,
    gpu=PROFILE["gpu"],
    volumes={
        "/root/.cache/huggingface": hf_cache_vol,
        "/root/.cache/vllm": vllm_cache_vol,
    },
    secrets=[hf_secret],
    scaledown_window=5 * MINUTES,   # idle → scale to zero after 5 min (dev = effectively free)
    timeout=30 * MINUTES,
    # Dev: scale to zero. For the live demo, redeploy with MODAL_MIN_CONTAINERS=1 so the
    # judged run has ZERO cold-start latency, then set it back to 0 to stop billing.
    min_containers=int(os.environ.get("MODAL_MIN_CONTAINERS", "0")),
)
@modal.concurrent(max_inputs=16)  # continuous batching for the heartbeat's concurrent sub-agents
@modal.web_server(port=VLLM_PORT, startup_timeout=15 * MINUTES)
def serve() -> None:
    """Launch vLLM's OpenAI-compatible server; Modal proxies :8000 as the web endpoint."""
    cmd = [
        "vllm", "serve", PROFILE["checkpoint"],
        "--revision", MODEL_REVISION,
        "--served-model-name", SERVED_NAME,
        "--host", "0.0.0.0", "--port", str(VLLM_PORT),
        "--tensor-parallel-size", "1",              # Nano fits one GPU
        "--max-model-len", str(PROFILE["max_model_len"]),
        "--max-num-seqs", "16",
        "--gpu-memory-utilization", "0.90",
        "--kv-cache-dtype", PROFILE["kv_cache_dtype"],
        "--mamba-ssm-cache-dtype", "float32",       # hybrid SSM state precision
        "--enable-chunked-prefill",
        "--trust-remote-code",                       # custom hybrid arch
        "--reasoning-parser", "nano_v3",
        "--enable-auto-tool-choice",
        "--tool-call-parser", "qwen3_coder",
        # Match this to INFERENCE_API_KEY; Modal already fronts the network boundary.
        "--api-key", os.environ.get("INFERENCE_API_KEY", "airtight-local"),
    ]
    if USE_REASONING_PLUGIN:
        cmd += ["--reasoning-parser-plugin", "/root/nano_v3_reasoning_parser.py"]

    env = {**os.environ, **PROFILE["extra_env"]}
    print(f"▶ Serving {PROFILE['checkpoint']} on {PROFILE['gpu']} as '{SERVED_NAME}' :{VLLM_PORT}")
    subprocess.Popen(" ".join(cmd), shell=True, env=env)
