# Airtight — Plan Updates (2026-07-17)

Two decisions made after the initial docs were committed. Apply the edits below so the repo reflects them, then move to building.

---

## Decision 1 — Add vLLM (target the $500 "Best Use of vLLM" bounty)

**Why:** we already need a self-hosted open-model endpoint for the NemoClaw routing constraint (`inference.local`). Serving it with vLLM stacks the bounty onto infrastructure we're building anyway, and extends the core insight — the same model hop is now HiddenLayer-analyzed, OpenShell-pinned, **and** vLLM-served. Genuine "why": the heartbeat fans out concurrent retrieval sub-agents, which is exactly vLLM's continuous-batching strength. Compatibility confirmed (day-0 Nemotron 3 support). Full detail in `research/vllm.md`.

**Edits:**

- **README.md → tracks table:** change "targeted (3)" framing to note vLLM as a cross-cutting 4th prize, and add a row:
  `| **Best Use of vLLM** ($500) | Agent inference served on self-hosted vLLM behind inference.local; concurrent sub-agent retrieval exploits continuous batching; Nano = small-model-punch | cross-cutting |`
- **README.md → Stack decisions:** add `**Serving:** vLLM (OpenAI-compatible) on Brev GPU, behind inference.local` under Runtime.
- **docs/ARCHITECTURE.md → Fig. 1 reasoner tier:** annotate [04]/[05] as served by vLLM; note `inference.local → vLLM` in the pinned-inference line.
- **docs/ARCHITECTURE.md → §07 Model Choice:** add a sentence that all three models are served via vLLM, and add the VRAM caveat (serve Nano as the guaranteed path).
- **docs/BUILD-PLAN.md → milestones:** insert **M1b — stand up vLLM behind `inference.local`; verify OpenAI-compatible + concurrent batching under the heartbeat.**
- **docs/JUDGING-RUBRIC.md:** add the vLLM bounty and how we map to its criteria (efficiency / small-model punch / real integration).
- **research/vllm.md:** new file (provided).

---

## Decision 2 — Opportunity Mode (news → whitespace), as a funnel, NOT the benchmark

**Why:** a teammate suggested also finding valuable *unpatented* whitespace / going off news. Good for commercial appeal (Antler) and adds a live-data flavor — but it must **not** become the benchmarked recursive task, because "worth patenting" and "not patented yet" have **no ground truth** you can score in a weekend, which would wreck the Track-1 delta.

**The framing that keeps it safe:** the recursive engine is the *same organ* for both jobs — a compounding prior-art matcher. Point it at an existing patent → report hits → loophole/invalidity report (measurable vs PTAB). Point it at a news-derived idea → report gaps → whitespace/patentability report. Whitespace is just the same prior-art muscle run in "find the hole" mode. So it's cheap to add and doesn't touch the measurable core.

**Scope guard:** don't build a news pipeline. One scripted headline for the demo is enough. Protect the hour that M4 (ablation) needs.

**Edits:**

- **docs/ARCHITECTURE.md → §02 Applicant Surface:** add an **Opportunity Mode** subsection — same engine, gap-mode output, one live-news demo beat. Explicitly state the benchmark stays on the loophole side.
- **docs/BUILD-PLAN.md → demo script:** add an optional 4th beat — "headline drops → agent flags emerging invention → runs prior-art engine in gap-mode → surfaces whitespace + a first loophole-free draft." Mark it **optional / only if M1–M6 are green.**
- **README.md → overview:** one line noting the engine runs in two modes (hit-mode = loopholes; gap-mode = whitespace).

---

## What to do next (priority order)

1. **Apply these edits + add the two new files.** ~15 min. Then stop writing docs.
2. **Scaffold the repo for building** — add a `src/` skeleton so the plan becomes code.
3. **Build M1 + M1b first** — OpenShell sandbox, agent routed to a vLLM-served Nemotron via `inference.local`. Proves capability + routing + vLLM in one shot.
4. **Build M4 next (highest leverage)** — the empty-vs-warmed ablation harness. It's the Track-1 proof AND the best demo moment. Everything else supports it.
5. Then M2 (HiddenLayer hooks), M3 (knowledge graph / RAG-from-self), M5 (policy), M6 (poisoned-doc + adversarial fixtures).
