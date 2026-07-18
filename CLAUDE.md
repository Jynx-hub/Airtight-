# CLAUDE.md — Airtight

Context for Claude Code sessions working in this project. Read `README.md` first for the overview, then this for how to work here.

## What this project is

Airtight is a **hackathon project**: an automated patent platform (two layers) targeting three tracks simultaneously — Recursive Intelligence, HiddenLayer Runtime Security, and NemoClaw + OpenShell Containment. See `README.md`.

This directory is the **single source of truth / context store** for the project. Everything about Airtight lives here. When you learn something new about the tools, the tracks, or a design decision, update the relevant file here rather than letting it evaporate.

## Ground truth is in `research/`

The four files in `research/` were produced from live web research on **2026-07-17** and contain the *accurate* API shapes and tool details — which differ from common assumptions. Before writing integration code, read the relevant briefing. Key corrections already captured:

- **HiddenLayer** — there is no product literally called "Runtime Security API." It's **AI Runtime Security**, powered by the **AIDR** engine, called through the **Interactions** API (`client.interactions.analyze(...)`). The response has **no scalar `verdict`** — derive the action from per-category `detected` flags in `analysis[]`. See `research/hiddenlayer.md`.
- **NemoClaw + OpenShell** are **real, shipping NVIDIA projects** (early preview, March 2026), not conceptual. OpenShell has **no `require_approval:` YAML key** — the human-in-the-loop boundary is a separate **Policy Advisor** flow (default-deny → agent proposes `addRule` → operator approves out-of-band → hot-reload → agent retries). The blueprint is graded as **four enforcement tiers** (filesystem / process / network / inference). See `research/nemoclaw-openshell.md`.
- **Model** — primary is **Nemotron 3 Super** (120B-A12B, **1M context**). Use reasoning-OFF / capped thinking budget on tool-call turns for deterministic function calling; reasoning-ON for claim drafting. See `research/nemotron.md`.
- **Serving** — Nemotron is served by **vLLM** (OpenAI-compatible) on **Modal's free tier** (serverless, scale-to-zero) behind `inference.local`; day-0 Nemotron 3 support confirmed. Still self-hosted vLLM, so the $500 bounty holds. Nano is the guaranteed path (L40S/FP8 fits VRAM); the free **NVIDIA NIM hosted endpoint** is the one-env-flip fallback. Brev is no longer available to us. See `research/vllm.md` + `docs/COSTS.md`.

## Design invariant (do not break)

Inference is **pinned to `inference.local`** and chosen by operator policy, not the agent. This is what lets HiddenLayer and OpenShell both enforce on the same model hop. Any change that lets the agent pick its own model endpoint breaks both the security and containment stories. Full wiring + the shared-doorway code contract: `docs/INFERENCE-LOCAL.md`.

Swapping backends is the operator's single env var — `INFERENCE_BACKEND=modal|nim` in `runtime/.env` — and **never automatic**. Do not add failover-on-error: a silent hop to the hosted NIM endpoint mid-demo swaps the judged self-hosted vLLM path for one that earns nothing, quietly voiding the $500 bounty evidence. Two gaps are recorded honestly in `docs/INFERENCE-LOCAL.md` rather than claimed: `inference.local` is still a naming contract with no gateway process, and provider creds are still read inside the sandbox. Both close at **F5**.

Shell scripts in `runtime/` load `.env` **non-destructively** — an already-exported var wins, matching `python-dotenv`'s default in the doorway. Never revert one to `set -a; . ./.env`: that overwrites exports, which silently made `INFERENCE_BACKEND=nim bash verify.sh` test Modal and pass.

## Conventions

- **LLM calls in this project route to Nemotron** (per the track constraint), not the workspace default (`gpt-5.4-mini` from the parent `~/CLAUDE.md`). This project is the exception — it must stay all-Nemotron / open-model for judging.
- Every model interaction must pass through the HiddenLayer wrapper. No raw model calls that bypass the bus.
- During policy dev, set OpenShell `enforcement: audit` first to observe the agent's real egress set, then flip to `enforce` for the judged run.
- **The Modal app stays PAUSED by default — GPU time is the scarcest resource on this project.** Un-pause only for a step that genuinely cannot be done without the GPU (a benchmark, a rehearsal, the judged demo), and re-pause the moment it's done. Never leave it running to "save time later"; an idle A100 bills at ~$2.50/hr against a fixed free credit, and the demo has to come out of that same pool. Pausing/un-pausing is the **operator's** call — ask, don't do it unprompted.
- **Build and validate against `runtime/mock_endpoint.py` before ever touching the live endpoint.** It's a stdlib OpenAI-compatible fake with simulated continuous batching, so harnesses, clients, and streaming logic can be debugged for free. Debugging on a metered cold start (~1–2 min on the `a100-bf16` default, ~12 min on `l40s-fp8`) is how the credit disappears. Get it green offline, then spend one short, fully-scripted live window.
- Check for concurrent sessions before a metered run. More than one agent working this repo can wake the app, redeploy it, or contaminate a measurement mid-window — `modal app list` shows live containers, and `runtime/bench.py` stamps a provenance note into every results file for exactly this reason.
- This repo lives at `github.com/Jynx-hub/Airtight-`. Commit locally as you work; ask before pushing.

## Build order (do not reorder)

1. M1 + M1b: OpenShell sandbox + agent routed to a vLLM-served Nemotron via inference.local
2. M4: empty-vs-warmed ablation harness (Track-1 proof + best demo) — highest leverage
3. M2 HiddenLayer hooks · M3 knowledge graph/RAG-from-self · M5 policy · M6 adversarial fixtures

Benchmark stays on loophole-finding (PTAB ground truth). Opportunity/whitespace mode is a demo funnel, not the benchmark.

## Current status

**Build started — inference spine is up and measured.** Lane A (Person 2 · Inference) has landed **F1** (Nemotron 3 Nano on vLLM → Modal free tier, `inference.local` reachable) and **F2** (the $500 vLLM bounty evidence): **10.67× aggregate throughput from continuous batching — 65.2 tok/s single-stream → 695.8 tok/s at concurrency 16**, with the curve kneeing at exactly the pinned `--max-num-seqs 16`. Numbers, method, and reproduction: `docs/THROUGHPUT.md`; harness `runtime/bench.py`; raw JSON `runtime/bench-results/`. That's **M1b** complete. **F3** is done too: backend routing is a single env var, `INFERENCE_BACKEND=modal|nim`, with all three paths (legacy/modal/nim) verified green end-to-end — models, chat, and tool-calling, with the doorway's `chat()` running unchanged across backends. **F4** is done, which closes the whole first half of Lane A: `runtime/RUNBOOK.md` is the team handoff (consumer quickstart needing no Modal account, the five-line demo-day card, the NIM flip). The re-benchmark it triggered changed the demo plan — **the judged profile is now `a100-bf16`, not `l40s-fp8`**. L40S/FP8 is genuinely faster *and* cheaper (865 vs 696 tok/s at C=16, $1.95 vs $2.50/hr), but its vLLM `init engine` takes 494–602s against the A100's 29s, so a **cold start is ~12 min, not the ~2–5 min every doc claimed** — measured twice, with weights and compile cache both warm. Modal preempted a container the same session, so recovery time, not price, picks the demo GPU. Both profiles stay on record: batching holds at **9.4–11× across two GPUs, two precisions, two attention backends**. Next on Lane A: the OpenShell locks **F5–F7**.

**Known bug (found during F2, not blocking):** with reasoning off, the *streaming* path routes all output to `reasoning_content` and leaves `content` empty — `runtime/nano_v3_reasoning_parser.py` only overrides the non-streaming `extract_reasoning`. Non-streaming callers (including the doorway's `chat()`) are fine. Anything streaming `delta.content` — Lane C's UI — will read empty. See `docs/THROUGHPUT.md` §Open issue. Lanes Data / Surface / Agent are still architecture/planning — nothing built there yet. The live checklist of record is `docs/WORKSTREAMS.md`.

Build order and the winning demo are in `docs/BUILD-PLAN.md`. After the inference spine, the highest-leverage build is the eval-harness ablation (M4): same invention, same Nemotron model, memory graph empty vs. warmed — it's the Track-1 proof and the strongest demo moment.

The official 100-point judging rubric — and how each Airtight decision maps to a scoring line — is in `docs/JUDGING-RUBRIC.md`. Optimize build effort against it; M4 scores on four lines at once.
