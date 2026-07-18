# CLAUDE.md — Airtight

Context for Claude Code sessions working in this project. Read `README.md` first for the overview, then this for how to work here.

## What this project is

Airtight is a **hackathon project**: an automated patent platform (two layers) targeting three tracks simultaneously — Recursive Intelligence, HiddenLayer Runtime Security, and NemoClaw + OpenShell Containment. See `README.md`.

This directory is the **single source of truth / context store** for the project. Everything about Airtight lives here. When you learn something new about the tools, the tracks, or a design decision, update the relevant file here rather than letting it evaporate.

## Ground truth is in `research/`

The three files in `research/` were produced from live web research on **2026-07-17** and contain the *accurate* API shapes and tool details — which differ from common assumptions. Before writing integration code, read the relevant briefing. Key corrections already captured:

- **HiddenLayer** — there is no product literally called "Runtime Security API." It's **AI Runtime Security**, powered by the **AIDR** engine, called through the **Interactions** API (`client.interactions.analyze(...)`). The response has **no scalar `verdict`** — derive the action from per-category `detected` flags in `analysis[]`. See `research/hiddenlayer.md`.
- **NemoClaw + OpenShell** are **real, shipping NVIDIA projects** (early preview, March 2026), not conceptual. OpenShell has **no `require_approval:` YAML key** — the human-in-the-loop boundary is a separate **Policy Advisor** flow (default-deny → agent proposes `addRule` → operator approves out-of-band → hot-reload → agent retries). The blueprint is graded as **four enforcement tiers** (filesystem / process / network / inference). See `research/nemoclaw-openshell.md`.
- **Model** — primary is **Nemotron 3 Super** (120B-A12B, **1M context**). Use reasoning-OFF / capped thinking budget on tool-call turns for deterministic function calling; reasoning-ON for claim drafting. See `research/nemotron.md`.

## Design invariant (do not break)

Inference is **pinned to `inference.local`** and chosen by operator policy, not the agent. This is what lets HiddenLayer and OpenShell both enforce on the same model hop. Any change that lets the agent pick its own model endpoint breaks both the security and containment stories.

## Conventions

- **LLM calls in this project route to Nemotron** (per the track constraint), not the workspace default (`gpt-5.4-mini` from the parent `~/CLAUDE.md`). This project is the exception — it must stay all-Nemotron / open-model for judging.
- Every model interaction must pass through the HiddenLayer wrapper. No raw model calls that bypass the bus.
- During policy dev, set OpenShell `enforcement: audit` first to observe the agent's real egress set, then flip to `enforce` for the judged run.
- Don't commit — this repo isn't initialized as its own git yet; it currently sits as an untracked folder under `~/` like the other workspace projects. Ask before `git init` or committing.

## Current status

**Architecture / planning phase — nothing built.** Build order and the winning demo are in `docs/BUILD-PLAN.md`. Start with the eval-harness ablation (M4): same invention, same Nemotron model, memory graph empty vs. warmed — it's the Track-1 proof and the strongest demo moment.
