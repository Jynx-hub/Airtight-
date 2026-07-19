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
  default **A100** rate (~$2.50/hr), roughly **~12 GPU-hours** — more than a hackathon of
  bursty dev needs.
- **The one paid moment is the demo.** Pin a warm replica only for the judged window
  (`MODAL_MIN_CONTAINERS=1 bash runtime/modal-deploy.sh`) so there's no cold-start on
  stage, then set it back to `0`. That's ~$2.50/hr for an hour, still inside the credit.
  Go through the script, never bare `modal deploy` — see `runtime/RUNBOOK.md`.

## GPU profile (cost vs quality)

Set `MODAL_GPU_PROFILE` in `runtime/.env`:

| Profile | GPU | Precision | ~Rate | tok/s @ C=16 | Cold start | When |
|---|---|---|---|---|---|---|
| `a100-bf16` *(default)* | A100 80 GB | BF16 | ~$2.50/hr | 695.8 | **~1–2 min** | **The judged path** — chosen for recovery time |
| `l40s-fp8` | L40S 48 GB | FP8 | ~$1.95/hr | **865.2** | **~12 min** | Dev/bulk — cheaper *and* faster to run |

Counter-intuitively the cheaper GPU is also the faster one (+24% throughput at C=16), so
for dev and any batch work `l40s-fp8` is the better buy. It is **not** the demo profile:
its vLLM engine init takes 494–602s versus the A100's 29s, so a preemption or an unpinned
container costs ~12 minutes of dead air. Both measured 2026-07-18 — `docs/THROUGHPUT.md`.

## Spend ledger

Modal bills per-second only while a container is up. Log every metered window here.

| Date | What | GPU | Billed time | ~Cost |
|---|---|---|---|---|
| 2026-07-18 05:5x–06:2x UTC | F2 throughput sweeps (runs A + B) + cold starts | A100 | ~30 min | ~$1.25 |
| 2026-07-18 06:43–07:21 UTC | F4 L40S re-benchmark: 2 cold starts + sweep | L40S | ~37 min | ~$1.20 |
| 2026-07-18 04:26 CDT | M4 ablation `20260718-042609`, 4 arms (1.8 min drafting) | A100 | ~8 min † | ~$0.35 † |
| 2026-07-18 12:28 CDT | M4 ablation `20260718-122807`, 12 arms (7.9 min drafting) | A100 | ~25 min † | ~$1.05 † |
| 2026-07-18 18:38 CDT | M4 ablation `20260718-183817`, 20 arms — **no usable number** (scoring asymmetry) | A100 | ~35 min | ~$1.50 |
| 2026-07-18 19:22 CDT | Rejudge `20260718-192244` — re-scored the banked drafts, no re-drafting | A100 | ~7 min | ~$0.30 |

† Wall-clock reconstructed from `drafting_seconds` in `results.json` plus judging and
cold-start overhead, at the ~3.3x drafting→wall ratio the `183817` run recorded. The last
two rows are measured. `results/ablation/latest/` is a copy of `183817`, not a fifth run.

**Running total ≈ $5.65** of the ~$30 credit. The judged demo window (~1 hr pinned warm on
A100) is budgeted at ~$2.50, leaving ample headroom for rehearsals.

📌 **The four ablation/rejudge rows were reconstructed on 2026-07-18, after the fact.** The
ledger had drifted to reporting only the F2/F4 benchmark windows while four metered live
runs went unlogged — a $3.20 gap on a fixed credit. Log the window when you close it, not
when someone notices.

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
- **Deploy-time env doesn't reach the Modal container** — latent, currently harmless, will
  bite. `modal_app.py` bakes `MODAL_GPU_PROFILE` into the image (line ~74) precisely because
  local env vars don't cross into the container — but `--api-key` and `--served-model-name`
  still read `os.environ` *inside* the container, where neither is set. So the deployed
  server always uses the literal defaults `airtight-local` / `nemotron`. That happens to
  match `runtime/.env` today, which is why nothing is broken. Change either value expecting
  the server to follow and every client call 401s. Fix with a **Modal Secret**
  (`modal secret create airtight-inference INFERENCE_API_KEY=…`) rather than an image bake —
  a bake would write the key into an image layer. Needs a redeploy, so it was deferred.
- **NIM Nano slug + reasoning toggle** — ✅ resolved (F3, 2026-07-18): the slug
  `nvidia/nemotron-3-nano-30b-a3b` is live, and NIM accepts
  `chat_template_kwargs.enable_thinking` in `extra_body` without a 400 — no `/no_think`
  directive needed. The doorway's `chat()` runs unchanged against both backends: both
  reasoning modes and tool-calling verified green on Modal *and* NIM.
- **NIM rate limit** — free tier is 1,000 inference credits and **40 requests/minute**. That
  RPM cap is why NIM is break-glass rather than a performance-equivalent swap: Modal's vLLM
  serves 16 concurrent requests with continuous batching (10.67×, `docs/THROUGHPUT.md`),
  so a fallback during a fan-out heartbeat will rate-limit, not merely run slower.
