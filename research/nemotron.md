# Research — Nemotron model choice (for Airtight)

*Verified 2026-07-17. Recommendation for an agentic patent-drafting + prior-art + self-improving-KB system.*

## Recommendation (TL;DR)
- **Primary reasoner / tool-caller:** **Nemotron 3 Super (120B total / 12B active, 1M context).**
- **Cheap sub-agent** (retrieval routing, source summarization into the KB, local iteration): **Nemotron 3 Nano (31.6B / ~3.6B active, 1M context).**
- **Rock-solid hosting fallback:** **Llama-3.3-Nemotron-Super-49B v1.5 (128K).**

All open (NVIDIA Open Model License), hosted on build.nvidia.com / NIM → Nemotron is a fully defensible primary for the "route to Nemotron / open models" constraint, at zero capability compromise.

## Two overlapping generations (as of mid-2026)
1. **Original Llama Nemotron** — Nano 8B / Super 49B / Ultra 253B (March 2025); first open models with a dynamic reasoning on/off toggle.
2. **Nemotron 3** — Nano / Super / Ultra (hybrid Mamba-Transformer MoE, **1M-token context**, purpose-built for long-horizon agentic work).

### Nemotron 3 family (newest — agent-native)
| Model | Params (total/active) | Context | Reasoning | Agentic / tool use | Access |
|---|---|---|---|---|---|
| **Nemotron 3 Nano** | 31.6B / ~3.6B (MoE) | 1M | ON/OFF + configurable thinking budget | AIME25 99.17% w/ tools; ~3.3× throughput vs Qwen3-30B | HF, build.nvidia.com, OpenRouter, llama.cpp/LM Studio; single GPU / laptop; ~Dec 2025 |
| **Nemotron 3 Super** | 120B / 12B (Latent MoE) | **1M native (BF16)** | strong; excels reasoning/coding/long-ctx | "best open model in its class" for agentic; ~5× throughput vs prior Super | HF, **NIM, build.nvidia.com**, OpenRouter, Fireworks, DeepInfra, Baseten…; Blackwell-optimized (NVFP4); Mar 11 2026 |
| **Nemotron 3 Ultra** | 550B / 55B (MoE) | 262k BF16, 1M w/ NVFP4 on Blackwell | frontier | built for long-running multi-agent | HF, NIM, OpenRouter; **self-host Blackwell-only** (B200/B300); Jun 4 2026 |

Nemotron 3 adds **multi-environment RL via NeMo Gym** to align to real multi-step agentic/tool-use tasks — directly relevant.

### Original Llama Nemotron (March 2025 — stable, widely hosted)
| Model | Params | Context | Notes |
|---|---|---|---|
| Nano 8B | 8B (Llama 3.1 8B) | 128K | edge/PC |
| **Super 49B → v1.5** | 49B (Llama 3.3 70B) | 128K | post-trained for reasoning + RAG + **tool calling**; fits one H100 |
| Ultra 253B | 253B (Llama 3.1 405B) | 128K | one 8×H100 node; beats DeepSeek-R1 with higher throughput |

### Other variants
- **Nemotron Nano 2 / 9B-v2** — 9B hybrid, 128K, tool use, ~6× throughput vs Qwen3-8B. Good tiny/on-device.
- **Nemotron-H** — research base (hybrid Mamba-Transformer); foundation of Nemotron 3, not a product to deploy directly.
- **Nemotron-4 340B** (June 2024) — older dense base/instruct/reward; **not reasoning/agent-tuned — skip** (mainly synthetic-data / reward model now).

## Why Nemotron 3 Super wins for Airtight
- **Long context is the hard requirement, Super gives 1M natively.** Patent families, full specs, and stacks of prior art blow past 128K fast. 1M keeps the target application, cited art, and working notes in-context instead of over-chunking — and chunking is exactly where loophole/edge-case reasoning breaks.
- **Multi-step reasoning without paying every turn.** Reasoning toggle + thinking budget → deep chains for claim drafting/loophole analysis, then fast deterministic mode for tool-call turns and KB writes.
- **Agentic tool calling is first-class, RL-trained** (NeMo Gym); rated best-in-class open for agentic tasks — needed to drive prior-art APIs, retrieval, KB updates reliably.
- **12B active params** → single-node throughput and low cost, unlike Ultra's Blackwell-only self-host friction. Broadly hosted, so a hackathon just hits an endpoint.

Use **Ultra 550B** only via a hosted NIM/OpenRouter endpoint (don't self-host without Blackwell) if you want max reasoning accuracy. Use **Nano** as the cheap fast sub-agent.

## vs. open alternatives
| Model | Reasoning | Long context | Tool/agentic | Note |
|---|---|---|---|---|
| **Nemotron 3 Super** | very strong (toggle+budget) | **1M** | **best-in-class open**, RL-trained | sweet spot; single-node; NVIDIA-hosted open endpoints |
| Qwen 3.5 (~122B) / Qwen3 | strong | 128K–256K | good | closest open competitor; weaker ultra-long ctx; not the named-constraint model |
| DeepSeek V4 / R1 | frontier raw reasoning | large | good, less tool-tuned OOB | heavier to serve; more agent scaffolding needed |
| Llama 3.x / 4 | solid, behind frontier agentic | 128K–10M (marketing) | OK | fine base (Nemotron built on it); weaker frontier reasoning/agentic |
| Mistral (Large/Magistral) | decent | 128K | OK | reasonable EU-hosted fallback; trails on agentic tool calling |

Nemotron differentiators that matter here: **native 1M context, reasoning on/off + thinking-budget cost control, RL-trained tool calling, first-party open hosted endpoints.**

## Routing plan (satisfies the constraint cleanly)
- **Primary:** Nemotron 3 Super (120B-A12B) via build.nvidia.com/NIM or OpenRouter/Fireworks — main reasoner + tool caller.
- **Sub-agent / KB loop:** Nemotron 3 Nano (31.6B-A3.6B) — retrieval routing, source summarization into the self-improving KB, local dev.
- **Fallback (still Nemotron):** Llama-3.3-Nemotron-Super-49B v1.5 (128K, explicit tool-calling post-training, single H100) if a v3 endpoint is flaky.
- **Optional hybrid:** wire one non-Nemotron open model (Qwen 3.5 / DeepSeek V4) as a *break-glass* route only — not needed to meet the constraint; staying all-Nemotron is cleaner for judging.

**Implementation note:** Nemotron models emit reasoning traces — use the vendor chat template + the Nemotron tool-call parser in vLLM/SGLang/NIM, and prefer **reasoning-OFF or capped thinking budget on tool-call turns** for deterministic function calling.

## Caveats
- Nemotron 3 Ultra vs DeepSeek V4 / Qwen 3.5 head-to-heads **not yet independently reproduced** — verify against technical reports / Artificial Analysis before quoting scores.
- Ultra self-hosting is **Blackwell-only** right now (Hopper planned) — consume via hosted endpoint.
- Newest context-window figures come from launch material — confirm the **served** context on your chosen endpoint (hosts sometimes cap below native 1M).

## Sources
NVIDIA Technical Blog (Llama Nemotron reasoning models; Nemotron 3 Super; Ultra accuracy); NVIDIA Newsroom (Nano/Super/Ultra launch); arXiv 2505.00949 (Llama-Nemotron), 2606.15007 (Nemotron 3 Ultra); build.nvidia.com + HF model cards (Llama-3.3-Nemotron-Super-49B-v1.5); HF blog (Nemotron 3 Nano); NVIDIA Research Nemotron-3 / ADLR pages; GitHub NVIDIA-NeMo/Nemotron; Artificial Analysis comparisons.
