# vLLM — Research Briefing

*Verified 2026-07-17. Drop in at `research/vllm.md`.*

## What it is

vLLM is **open-source inference/serving software you run yourself on a GPU** — not a hosted API. You install it, point it at a model, and it stands up an **OpenAI-compatible HTTP server**. The agent then calls that endpoint exactly like it would call OpenAI, at a URL you own. Its performance edge comes from **continuous (in-flight) batching** and **PagedAttention**, which give high throughput under many concurrent requests.

## Why it belongs in Airtight (the "why" the bounty rewards)

We already need a self-hosted open-model endpoint — the NemoClaw routing constraint pins inference to `inference.local`, and that endpoint has to be *something*. Making it **vLLM** means the bounty stacks onto infrastructure we're building anyway.

It extends the core architectural insight: `inference.local` is now **HiddenLayer-analyzed, OpenShell-pinned, and vLLM-served** — one model hop, one boundary, four prizes.

The bounty weights **efficiency under concurrent load** and the **small-model punch**. Our design hits both natively:

- The recursive engine is **heartbeat-driven and fans out concurrent prior-art retrieval sub-agents** → exactly the continuous-batching workload vLLM is built for. Throughput genuinely matters in the loop; it is not decorative.
- The **Nemotron 3 Nano sub-agent tier** is the "small model punching above its size" story — cheap concurrent retrieval on vLLM while Super does heavy drafting.

## Compatibility — confirmed

vLLM shipped **day-0 support for Nemotron 3** (hybrid Mamba-Transformer MoE). There is an official vLLM blog + cookbook, *"Run Highly Efficient and Accurate Multi-Agent AI with Nemotron 3 Super Using vLLM,"* with continuous-batching and streaming configs. Serving our primary model on vLLM is a documented path, not a gamble.

## How we host it (event-day plan)

**Brev is no longer available to us** — we host on **Modal's free tier** instead. It's serverless GPU with **scale-to-zero**, so you pay (out of the free monthly credit) only while a request runs, and it's still *self-hosted vLLM* → the $500 bounty is intact. Full cost/free-tier plan: `docs/COSTS.md`.

1. **Deploy to Modal** — `runtime/modal_app.py` runs `vllm serve` on a Modal GPU and exposes an OpenAI-compatible web endpoint. `bash runtime/modal-deploy.sh` (needs a free Modal account + an HF token stored as a Modal Secret for the gated weights). Default GPU profile is **A100-80GB + BF16 Nano** — the judged path, picked for cold-start recovery once both profiles were measured on 2026-07-18 (`docs/THROUGHPUT.md`). L40S + FP8 is cheaper and faster to run but cold-starts in ~12 min, so it's the dev/bulk profile.
2. vLLM downloads the weights (cached in a Modal Volume so cold starts don't re-download) and serves on `:8000`, which Modal proxies as `https://<workspace>--airtight-nemotron-serve.modal.run`.
3. Point `inference.local` at that URL. The route is **operator-pinned**, so the agent inside the OpenShell sandbox cannot repoint it — that's the containment property. vLLM is the engine; `inference.local` is the locked pipe to it.
4. **Fallback:** the free **NVIDIA NIM hosted endpoint** (`integrate.api.nvidia.com`, model `nvidia/nemotron-3-nano-30b-a3b`) — a one-env-flip swap if Modal is cold or credits run out. Hosted, so it doesn't count toward the bounty; it's the safety net.

## Model / hardware plan (reliability first)

| Path | Model on vLLM | Notes |
|---|---|---|
| **Guaranteed demo path** | Nemotron 3 Nano (31.6B / ~3.2B active) | small, fast, single GPU; directly demonstrates the small-model-punch criterion |
| **Primary if hardware allows** | Nemotron 3 Super (120B / ~12.7B active) | day-0 vLLM support; needs enough VRAM to *hold* all params even at 12B active → beefy/multi-GPU |
| **Safety net** | Llama-3.3-Nemotron-Super-49B v1.5 (128K) | standard transformer, single H100, runs cleanly on vLLM — still Nemotron, bounty intact |

**Key caveat — VRAM:** even at ~12B active, the 120B MoE must hold all params in memory, which needs a big (multi-GPU) box. Serve **Nano on vLLM as the guaranteed path** — the FP8 checkpoint fits one L40S (48 GB) on Modal; bring up Super only if a larger box lands.

## Milestone impact

Adds one milestone — **M1b: stand up vLLM behind `inference.local`; verify OpenAI-compatible + concurrent batching under the heartbeat.** Everything downstream is unchanged.

## To confirm on the day

- Exact `vllm serve` flags for the chosen Nemotron variant (check the vLLM Nemotron 3 cookbook) — and whether your pinned vLLM ships the `nano_v3` reasoning parser built-in or needs the plugin file.
- ~~The Modal GPU profile~~ — **settled 2026-07-18**: `a100-bf16` is the default and the judged profile (`docs/THROUGHPUT.md`). Still confirm the free monthly credit covers your dev + demo hours (`docs/COSTS.md`).
- That the OpenShell egress route to the Modal (or NIM) host is on the allowlist (read/inference egress), and that the agent cannot repoint it.

## Sources

- vLLM × Nemotron 3 Super multi-agent cookbook — <https://vllm.ai/blog/2026-03-11-nemotron-3-super>
- vLLM day-0 Nemotron 3 (Ultra) support — <https://vllm.ai/blog/2026-06-04-nemotron-3-ultra-vllm>
- Disaggregated serving for hybrid SSM models in vLLM — <https://vllm.ai/blog/2026-04-21-hybrid-ssm-disagg>
- Nemotron 3 Super deployment guide — <https://www.spheron.network/blog/nemotron-3-super-deployment-guide/>
