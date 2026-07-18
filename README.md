# Airtight

> **Working codename** — the pitch is a patent with no air in it: no gaps a competitor can slip through. Swap freely (Ironclad, Claimsmith, Priora).

An automated **patent platform** with two layers:

1. **Applicant Surface** — the user-facing product: a light intake captures an invention idea, the system drafts a full patent, the user receives a filing-ready specification. Same lane as [autoinvent.com](https://www.autoinvent.com/).
2. **Examiner Engine** — the self-improving, secured backend that wins the hackathon tracks: an autonomous agent that mines patent data + examiner rejections for the **edge cases people exploit as loopholes**, compounds them into a persistent knowledge graph, and drafts each new patent against the accumulated failure library.

The engine runs in two modes: **hit-mode** (point it at an existing patent → loophole/invalidity report — the benchmarked core) and **gap-mode** (point it at a news-derived idea → whitespace/patentability report — a demo funnel, not the benchmark).

**Domain:** the inventions are **software & electronics** patents. The whole pipeline — prior-art search, claim drafting, the edge-case knowledge graph, and the correctness checks — is scoped to that space; §101 eligibility (Alice/Mayo) and §112(f) means-plus-function are first-class failure modes here, and mechanical/chemical/biotech patent conventions don't apply.

**The wedge:** the three ways patents fail in the real world — **loopholes** (claim language a competitor designs around), **time** (weeks of attorney drafting), **incorrectness** (§101 subject-matter eligibility, §112 indefiniteness, antecedent-basis gaps, prior-art anticipation).

---

## Hackathon tracks targeted (3 + a cross-cutting 4th prize)

| Track | How Airtight fits | Ceiling |
|-------|-------------------|---------|
| **Recursive Intelligence** | Edge-case knowledge graph + episodic memory + RAG-from-self; measurable first-run vs last-run delta on loopholes-caught / time / correctness | 9/10 |
| **HiddenLayer Runtime Security** | Every interaction (prompt, response, tool call, tool result, ingested doc) routed through HiddenLayer AIDR; graded response policy | 9/10 |
| **NemoClaw + OpenShell Containment** | Capable agent (live filing creds + client datastore) contained by a 3-tier OpenShell policy with Policy-Advisor human-in-the-loop | 8/10 |
| **Best Use of vLLM** ($500) | Agent inference served on self-hosted vLLM behind inference.local; concurrent sub-agent retrieval exploits continuous batching; Nano = small-model-punch | cross-cutting |

## Stack decisions

- **Model:** Nemotron 3 Super (120B-A12B, 1M ctx) primary · Nemotron 3 Nano sub-agent · Llama-3.3-Nemotron-Super-49B fallback
- **Runtime:** NVIDIA OpenShell sandbox, stood up by NemoClaw; inference pinned to `inference.local`
- **Serving:** vLLM (OpenAI-compatible) on Brev GPU, behind `inference.local`
- **Security:** HiddenLayer AI Runtime Security (AIDR engine, Interactions API)
- **Harness:** LangChain Deep Agents / OpenClaw (NemoClaw-supported)

**The one architectural insight:** inference is pinned to `inference.local` (operator-chosen, not agent-chosen), so HiddenLayer's security bus and OpenShell's containment boundary converge on the *same* model hop — **one boundary, three tracks.**

---

## What lives here

```
Airtight/
├── README.md                         ← you are here (overview + index)
├── CLAUDE.md                         ← context for Claude Code sessions in this repo
├── airtight/                         ← shared package: the doorway (one model hop) + data shapes
├── agent/                            ← Person 4: work loop, smoke runner (memory/eval land here)
├── data/                             ← Person 1: corpora, ground truth, fixtures
├── inference/                        ← Person 2: vLLM runbook, verify script, OpenShell policy draft
├── surface/                          ← Person 3: applicant surface (Next.js later)
├── tests/                            ← stub-mode smoke tests (no network needed)
├── docs/
│   ├── ARCHITECTURE.md               ← full spec: concept, layers, FIG.1, 3 claims, model, judge's read, build & demo, sources
│   ├── BUILD-PLAN.md                 ← milestones M1–M6, demo script, self-assessment
│   ├── INFERENCE-LOCAL.md            ← the one boundary: wiring, invariant, shared-doorway contract
│   ├── JUDGING-RUBRIC.md             ← official 100-pt scorecard + how Airtight maps to it
│   ├── WORKSTREAMS.md                ← plain-English who-builds-what plan
│   └── SESSIONS.md                   ← per-milestone Claude Code kickoff prompts
└── research/                         ← grounded briefings (verified 2026-07-17)
    ├── hiddenlayer.md                ← AIDR Interactions API: endpoints, payloads, auth, SDK
    ├── nemoclaw-openshell.md         ← blueprint tiers, policy YAML schema, Policy Advisor, CLI
    ├── nemotron.md                   ← model lineup + recommendation
    └── vllm.md                       ← vLLM serving: why, compatibility, Brev hosting, VRAM caveats
```

**Shareable artifact:** https://claude.ai/code/artifact/5ccf4150-8223-4eca-bc0d-2516184a4092

## Status

**Phase: build.** The shared scaffold is in `main`: doorway + shapes (`airtight/`), a stub-mode agent loop (`agent/`), and Person 2's vLLM/OpenShell handoff (`inference/`). Everything runs green with `pytest tests/` and `python -m agent.run_smoke` — no network needed. Next: Person 2 stands up vLLM on Brev (M1b), then the eval-harness ablation (`docs/BUILD-PLAN.md` → M4) — the Track-1 proof and the best demo moment.

Quick start: `python3 -m venv .venv && .venv/bin/pip install -e ".[dev]" && .venv/bin/pytest tests/`
