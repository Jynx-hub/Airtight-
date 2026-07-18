# Airtight — Cost & Free-Tier Plan

**Bottom line: this project runs on ~$0 out of pocket for the hackathon.** Brev is no
longer available to us, so hosting moved to a free-tier stack. The only line that isn't
free is GPU inference, and scale-to-zero keeps that inside a free monthly credit. This
doc is the single source of truth for what costs what and the two things to confirm before
relying on $0.

## The free-tier stack

| Tier | Backend | Cost | Keeps $500 vLLM bounty? | Role |
|---|---|---|---|---|
| **1 — Primary** | **Modal** serverless vLLM serving Nemotron 3 Nano (`runtime/modal_app.py`) | ~$0 under Modal's free monthly credit; scale-to-zero | ✅ yes — self-hosted vLLM | Judged run + concurrency numbers |
| **2 — Fallback / free dev** | **NVIDIA NIM** hosted endpoint (`integrate.api.nvidia.com`) | Free dev credits (`nvapi-…` key) | ❌ no — hosted API | Dev iteration + "Modal is cold" break-glass |
| **3 — Break-glass** | Any OpenAI-compatible local server (env flip only) | $0 | ❌ | Offline dev; no build effort |

Tiers swap with a **one-var flip** in `runtime/.env` — `INFERENCE_BACKEND=modal|nim`. Both
credential sets stay side by side, so flipping never destroys the other one's key and the
doorway (`runtime/inference_local.py`) needs no code change. There is no automatic failover:
a silent hop to a hosted tier would void the bounty evidence, so falling back is an operator
act. Prove it: `bash runtime/serve-nim.sh`.

## Why Modal is effectively free

- **Scale-to-zero.** `min_containers=0` + a 5-min idle window → the GPU spins up on the
  first request and shuts down after the last one. You only spend credit while a request
  is actually running. Intermittent dev over a weekend is single-digit GPU-hours.
- **Free monthly credit** (~$30, *verify current figure* at modal.com/pricing) buys, at the
  default **L40S** rate (~$1.95/hr), roughly **~15 GPU-hours** — more than a hackathon of
  bursty dev needs.
- **The one paid moment is the demo.** Pin a warm replica only for the judged window
  (`MODAL_MIN_CONTAINERS=1 modal deploy`) so there's no cold-start on stage, then set it
  back to `0`. That's ~$2/hr for an hour, still inside the credit.

## GPU profile (cost vs quality)

Set `MODAL_GPU_PROFILE` in `runtime/.env`:

| Profile | GPU | Precision | ~Rate | When |
|---|---|---|---|---|
| `l40s-fp8` *(default)* | L40S 48 GB | FP8 | ~$1.95/hr | Cheapest fit for Nano — the default |
| `a100-bf16` | A100 80 GB | BF16 | ~$2.50/hr | Max-quality path; one env flip |

## The one thing that could push cost up

**A forgotten warm replica or a rented always-on box.** Modal scale-to-zero avoids this by
default — the failure mode is leaving `MODAL_MIN_CONTAINERS=1` on after the demo, or
renting a separate always-on GPU (Vast/RunPod) and not stopping it. Flip back to `0` after
the demo and there's nothing to leak.

## Everything else is already free

- **HiddenLayer** (AI Runtime Security / Interactions API) — sponsor/hackathon access. **⚠ Confirm a key was actually issued** — this is the one assumed-$0 to verify.
- **NemoClaw + OpenShell** — open-source / NVIDIA early preview.
- **Prior-art / patent APIs** (PatentsView, EPO OPS, Google Patents) — free public endpoints.
- **Embeddings / RAG** — run on the GPU we're already renting; no separate API.
- **Demo frontend** — Vercel/Netlify free tier; `inference.local` is a local hostname, no domain.

## Two things to confirm before relying on $0

1. **Modal's current free credit** (modal.com/pricing) — the ~$30 figure is historically
   stable but verify it.
2. **HiddenLayer key in hand** — the only line above assumed free without a key issued.

## Possible second free pool

The retired Brev plan came with **$100/team-member in bounty credits**. Brev is an NVIDIA
product — **check whether those credits transferred to build.nvidia.com / NIM credits.** If
they did, dev on NIM is free and funded, and Modal is only for the live vLLM demo → total
spend approaches $0 with headroom to spare.

## Deploy-time flags to verify (from the build)

- **Modal decorator API** — `@app.function`+`@modal.concurrent`+`@modal.web_server` (used in
  `modal_app.py`) vs. a newer consolidated `@app.server` form; match the installed `modal`
  version's docs.
- **`nano_v3` reasoning parser** — ✅ resolved: `runtime/nano_v3_reasoning_parser.py` is the
  real plugin (fetched 2026-07-17 from the public NVIDIA HF repo). The recipe confirms
  `nano_v3` is **not** built-in for the pinned vLLM, so keep `USE_REASONING_PLUGIN=True`.
- **vLLM version pin** — ✅ resolved: `modal_app.py` pins `vllm==0.12.0` (recipe-recommended;
  0.11.2 is the minimum). Re-check the recipe if you change the checkpoint.
- **NIM Nano slug + reasoning toggle** — verify `nvidia/nemotron-3-nano-30b-a3b` and whether
  NIM honors `chat_template_kwargs.enable_thinking` or expects a `/no_think` directive.
