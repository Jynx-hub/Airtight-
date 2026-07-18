# CLAUDE.md — Airtight

Context for Claude Code sessions working in this project. Read `README.md` first for the overview, then this for how to work here.

## What this project is

Airtight is a **hackathon project**: an automated patent platform (two layers) targeting three tracks simultaneously — Recursive Intelligence, HiddenLayer Runtime Security, and NemoClaw + OpenShell Containment. See `README.md`.

This directory is the **single source of truth / context store** for the project. Everything about Airtight lives here. When you learn something new about the tools, the tracks, or a design decision, update the relevant file here rather than letting it evaporate.

## Domain scope — software & electronics patents

The inventions Airtight intakes, drafts, and analyzes are **software and electronics** patents. Everything downstream is scoped to that domain — prior-art search, claim drafting, the edge-case knowledge graph, and the correctness checks. Concretely this means the loophole/failure library skews toward the failure modes that dominate this space: **§101 subject-matter eligibility** (Alice/Mayo — abstract-idea and "do-it-on-a-computer" rejections), **§112(f) means-plus-function** traps from functional claiming, **§112 indefiniteness / antecedent-basis** gaps, and prior-art anticipation across fast-moving software/hardware art units. Do not assume mechanical, chemical, or biotech patent conventions.

## Ground truth is in `research/`

The four files in `research/` were produced from live web research on **2026-07-17** and contain the *accurate* API shapes and tool details — which differ from common assumptions. Before writing integration code, read the relevant briefing. Key corrections already captured:

- **HiddenLayer** — there is no product literally called "Runtime Security API." It's **AI Runtime Security**, powered by the **AIDR** engine, called through the **Interactions** API (`client.interactions.analyze(...)`). The response has **no scalar `verdict`** — derive the action from per-category `detected` flags in `analysis[]`. See `research/hiddenlayer.md`.
- **NemoClaw + OpenShell** are **real, shipping NVIDIA projects** (early preview, March 2026), not conceptual. OpenShell has **no `require_approval:` YAML key** — the human-in-the-loop boundary is a separate **Policy Advisor** flow (default-deny → agent proposes `addRule` → operator approves out-of-band → hot-reload → agent retries). The blueprint is graded as **four enforcement tiers** (filesystem / process / network / inference). See `research/nemoclaw-openshell.md`.
- **Model** — primary is **Nemotron 3 Super** (120B-A12B, **1M context**). Use reasoning-OFF / capped thinking budget on tool-call turns for deterministic function calling; reasoning-ON for claim drafting. See `research/nemotron.md`.
- **Serving** — Nemotron is served by **vLLM** (OpenAI-compatible) on **Modal's free tier** (serverless, scale-to-zero) behind `inference.local`; day-0 Nemotron 3 support confirmed. Still self-hosted vLLM, so the $500 bounty holds. Nano is the guaranteed path (L40S/FP8 fits VRAM); the free **NVIDIA NIM hosted endpoint** is the one-env-flip fallback. Brev is no longer available to us. Deploy: `runtime/modal_app.py`. See `research/vllm.md` + `docs/COSTS.md`.

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
- **Finish any task by updating `docs/WORKSTREAMS.md` in the same change that finishes it.** That file is the team's shared status board across four lanes — an unrecorded result is one a teammate re-does or a demo plans around wrongly. This applies to *anything* the file tracks: a lane item done, a status that shifted, a claim it makes that your work just falsified (a gitignore rule, a test count, a model alias, a cost estimate). Grep it for what you touched before calling the work done.
  - Respect the notation the file defines at its own head: `[x]` means **verified working**, `◐` means real code exists but the item's defining requirement is not met, and the status glyphs are ✅ done / ⚠️ caveat-or-blocker / 📌 operational note. Never promote `[ ]` or `◐` to `[x]` on the strength of code existing or tests passing — that file's rule is that boxes are checked against observed behaviour, not against what anyone reported. A green suite in stub mode proves plumbing, not the requirement.
  - Record partial and failed outcomes with the same care as wins, including what it cost and what is still open. The entries that have saved the most time here are the honest ones (the `--n 10` timeout stall, the L40S cold-start reversal) — they are why the next person doesn't burn GPU credit rediscovering them.
- This repo lives at `github.com/Jynx-hub/Airtight-`. Commit locally as you work; ask before pushing.

## Build order (do not reorder)

1. M1 + M1b: OpenShell sandbox + agent routed to a vLLM-served Nemotron via inference.local
2. M4: empty-vs-warmed ablation harness (Track-1 proof + best demo) — highest leverage
3. M2 HiddenLayer hooks · M3 knowledge graph/RAG-from-self · M5 policy · M6 adversarial fixtures

Benchmark stays on loophole-finding (PTAB ground truth). Opportunity/whitespace mode is a demo funnel, not the benchmark.

## Current status

**Build phase — inference spine measured and handed off; agent lane M1–M6 built.**

*Lane A (Person 2 · Inference):* **F1–F4 done — the whole first half of the lane.** Nemotron 3 Nano on vLLM → Modal free tier, and the $500 vLLM bounty evidence: **10.67× aggregate throughput — 65.2 tok/s single-stream → 695.8 tok/s at concurrency 16**, curve kneeing at the pinned `--max-num-seqs 16` (`docs/THROUGHPUT.md`; harness `runtime/bench.py`). That's **M1b**. Backend routing is a single env var `INFERENCE_BACKEND=modal|nim`, all three paths verified green. **F4** landed the team handoff — `runtime/RUNBOOK.md`, the consumer quickstart (no Modal account needed) plus the demo-day keep-warm card — and a re-benchmark that **changed the judged GPU profile to `a100-bf16`**: L40S/FP8 is genuinely faster *and* cheaper to run (865 vs 696 tok/s at C=16, $1.95 vs $2.50/hr) but cold-starts in **~12 min** against the A100's ~1–2 (vLLM engine init 494–602s vs 29.3s), and Modal preempted a container during the same session — so recovery time, not price, picks the demo GPU. The "~2–5 min cold start" in the old docs was wrong on both profiles. Weights are now pinned to a per-profile commit SHA so an upstream push can't move the model mid-demo. Open: OpenShell locks **F5–F7**.

Known non-blocking bug: with reasoning off the *streaming* path routes all output to `reasoning_content` and leaves `content` empty — `runtime/nano_v3_reasoning_parser.py` overrides only the non-streaming `extract_reasoning`, and that file is byte-identical to NVIDIA's, so the bug is **upstream**. Bites the Surface lane's streaming UI; the doorway's non-streaming `chat()` is unaffected. Workaround: read `delta.reasoning_content or delta.content`.

*Lane Agent (Person 4):* the doorway (`airtight/call_model`, the only legal model hop — HiddenLayer's slot is `_analyze`, reasoning toggle in `_reasoning_params`) + four shapes, the M1 loop, **M2** guardrails (all 5 hops), **M3** memory + episodic compounding, **M4** ablation harness, **M5/M6** containment sim (`containment/`). *Surface:* FastAPI starter (`surface/`). *Data:* live USPTO ODP puller (`data/pull_uspto.py`). Verify: `.venv/bin/pytest tests/` — **expect 74 passed** (0 skipped) with `.[dev,web,poison]`, stub mode, no network — `data/real/` now ships in the repo, so `test_real_pull_splits_cleanly` runs by default and only skips if you delete it. Drop an extra and its tests `importorskip`: `.[dev,web]` drops the E5 poison-PDF test (needs `pdfplumber`); `.[dev]` alone drops the surface tests too. A green run is not by itself proof coverage — check the count.

**Current focus — four blocks in `docs/WORKSTREAMS.md`:** (A) make OpenShell/NemoClaw actually enforce instead of `print()`, (B) make the loop recursive — it has no revise turn and episodic memory has never written a file, (C) finish retrieval — the statute-blind ranking that caused the backwards ablation is **fixed and offline-validated** (`d1c60b1`), leaving normalization, a write API and the knowledge-graph question, and (D) connect ingest to memory, which are today entirely disconnected. A3, B, C and D are all unblocked; only the sandbox items wait on hosted hardware. **The single highest-leverage item is now the GPU re-run** — both live ablation numbers were produced by retrieval that no longer exists, so neither is quotable until it lands.

The official 100-point judging rubric — and how each Airtight decision maps to a scoring line — is in `docs/JUDGING-RUBRIC.md`. Optimize build effort against it; M4 scores on four lines at once.
