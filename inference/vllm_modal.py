"""Serve Nemotron via vLLM on Modal as an OpenAI-compatible endpoint (M1b).

    pip install modal
    modal setup                       # one-time auth
    modal serve inference/vllm_modal.py   # dev: hot-reload, temporary URL
    modal deploy inference/vllm_modal.py  # stable URL for the team + demo

Deploy prints an HTTPS URL like
    https://<workspace>--airtight-vllm-serve.modal.run
Hand the team `<that URL>/v1` as AIRTIGHT_BASE_URL (see RUNBOOK.md §3).

Modeled on Modal's official vLLM example — https://modal.com/docs/examples/vllm_inference
UNVERIFIED against the current Modal SDK: the exact web-server decorator name
(@modal.web_server vs @app.server), some GPU flag spellings, and the vLLM /
Nemotron serve flags. Confirm against that example + the vLLM Nemotron cookbook
before the judged run, and fix HERE only — the doorway treats the URL as opaque.
"""

import subprocess

import modal

# --- model: Nano is the guaranteed path (fits one GPU); Super only if VRAM allows ---
MODEL = "nvidia/nemotron-3-nano-31b-a3b"  # UNVERIFIED id — check the server's /v1/models
N_GPU = 1
GPU = f"A100-80GB:{N_GPU}"  # Nano fits; for Super try "H200:2" and expect it to be tight
VLLM_PORT = 8000
MINUTES = 60

vllm_image = (
    modal.Image.from_registry("nvidia/cuda:12.9.0-devel-ubuntu22.04", add_python="3.12")
    .entrypoint([])
    .pip_install("vllm", "huggingface_hub")
)

# Cache weights on a Modal Volume so restarts don't re-download from HF.
hf_cache = modal.Volume.from_name("huggingface-cache", create_if_missing=True)

app = modal.App("airtight-vllm")


@app.function(
    image=vllm_image,
    gpu=GPU,
    volumes={"/root/.cache/huggingface": hf_cache},
    scaledown_window=15 * MINUTES,  # stay warm between requests; scales to zero after idle
    timeout=20 * MINUTES,
    min_containers=1,  # keep one replica hot through the demo (drop to 0 to save credits)
)
@modal.web_server(port=VLLM_PORT, startup_timeout=15 * MINUTES)
def serve():
    # vLLM's own OpenAI-compatible server. UNVERIFIED flags — confirm against the
    # vLLM Nemotron 3 cookbook (research/vllm.md sources).
    subprocess.Popen(
        [
            "vllm", "serve", MODEL,
            "--host", "0.0.0.0", "--port", str(VLLM_PORT),
            "--enable-auto-tool-choice",
            "--tool-call-parser", "nemotron",  # UNVERIFIED parser name
        ]
    )
