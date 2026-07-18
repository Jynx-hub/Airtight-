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

Serverless GPU via **Modal** (updated 2026-07-18 — replaces the earlier Brev-rental plan). Modal keeps the vLLM bounty (we still self-host vLLM, just on Modal's on-demand GPUs) while removing the babysit-a-box work: it scales to zero, autoscales under load, and gives a stable HTTPS endpoint. Deploy template: `inference/vllm_modal.py`.

1. **Deploy** — `pip install modal && modal setup`, then `modal deploy inference/vllm_modal.py`. Modal builds a CUDA image with vLLM, runs `vllm serve <model>` inside a serverless container, caches weights on a Modal Volume, and prints a stable HTTPS URL.
2. **Endpoint** — that URL serves the OpenAI-compatible API at `/v1`. `min_containers=1` keeps a replica warm for the demo (no cold start on stage); `scaledown_window` scales to zero when idle so credits only burn while serving.
3. Point `inference.local` at that URL. The route is **operator-pinned**, so the agent inside the OpenShell sandbox cannot repoint it — that's the containment property. vLLM is the engine; `inference.local` is the locked pipe to it.

Modal's official vLLM example (https://modal.com/docs/examples/vllm_inference) is the reference the template is built from.

## Model / hardware plan (reliability first)

| Path | Model on vLLM | Notes |
|---|---|---|
| **Guaranteed demo path** | Nemotron 3 Nano (31.6B / ~3.2B active) | small, fast, single GPU; directly demonstrates the small-model-punch criterion |
| **Primary if hardware allows** | Nemotron 3 Super (120B / ~12.7B active) | day-0 vLLM support; needs enough VRAM to *hold* all params even at 12B active → beefy/multi-GPU |
| **Safety net** | Llama-3.3-Nemotron-Super-49B v1.5 (128K) | standard transformer, single H100, runs cleanly on vLLM — still Nemotron, bounty intact |

**Key caveat — VRAM:** even at ~12B active, the 120B MoE must hold all params in memory. On a single Modal GPU that can be tight (Super wants multi-GPU, e.g. `gpu="H200:2"`). Serve **Nano on vLLM as the guaranteed path**; bring up Super only if the GPU allows.

## Milestone impact

Adds one milestone — **M1b: stand up vLLM behind `inference.local`; verify OpenAI-compatible + concurrent batching under the heartbeat.** Everything downstream is unchanged.

## To confirm on the day

- Exact `vllm serve` flags for the chosen Nemotron variant (check the vLLM Nemotron 3 cookbook) and the current Modal web-server decorator/GPU flags (check Modal's vLLM example).
- Available VRAM on the chosen Modal GPU before committing to Super vs Nano.
- That the OpenShell egress route to the vLLM host is on the allowlist (read/inference egress), and that the agent cannot repoint it.

## Sources

- vLLM × Nemotron 3 Super multi-agent cookbook — <https://vllm.ai/blog/2026-03-11-nemotron-3-super>
- vLLM day-0 Nemotron 3 (Ultra) support — <https://vllm.ai/blog/2026-06-04-nemotron-3-ultra-vllm>
- Disaggregated serving for hybrid SSM models in vLLM — <https://vllm.ai/blog/2026-04-21-hybrid-ssm-disagg>
- Nemotron 3 Super deployment guide — <https://www.spheron.network/blog/nemotron-3-super-deployment-guide/>
