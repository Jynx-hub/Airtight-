# Airtight

> **Working codename** — the pitch is a patent with no air in it: no gaps a competitor can slip through. Swap freely (Ironclad, Claimsmith, Priora).

An automated **patent platform** with two layers:

1. **Applicant Surface** — the user-facing product: a light intake captures an invention idea, the system drafts a full patent, the user receives a filing-ready specification. Same lane as [autoinvent.com](https://www.autoinvent.com/).
2. **Examiner Engine** — the self-improving, secured backend that wins the hackathon tracks: an autonomous agent that mines patent data + examiner rejections for the **edge cases people exploit as loopholes**, compounds them into a persistent knowledge graph, and drafts each new patent against the accumulated failure library.

**The wedge:** the three ways patents fail in the real world — **loopholes** (claim language a competitor designs around), **time** (weeks of attorney drafting), **incorrectness** (§112 indefiniteness, antecedent-basis gaps, prior-art anticipation).

---

## Hackathon tracks targeted (3)

| Track | How Airtight fits | Ceiling |
|-------|-------------------|---------|
| **Recursive Intelligence** | Edge-case knowledge graph + episodic memory + RAG-from-self; measurable first-run vs last-run delta on loopholes-caught / time / correctness | 9/10 |
| **HiddenLayer Runtime Security** | Every interaction (prompt, response, tool call, tool result, ingested doc) routed through HiddenLayer AIDR; graded response policy | 9/10 |
| **NemoClaw + OpenShell Containment** | Capable agent (live filing creds + client datastore) contained by a 3-tier OpenShell policy with Policy-Advisor human-in-the-loop | 8/10 |

## Stack decisions

- **Model:** Nemotron 3 Super (120B-A12B, 1M ctx) primary · Nemotron 3 Nano sub-agent · Llama-3.3-Nemotron-Super-49B fallback
- **Runtime:** NVIDIA OpenShell sandbox, stood up by NemoClaw; inference pinned to `inference.local`
- **Security:** HiddenLayer AI Runtime Security (AIDR engine, Interactions API)
- **Harness:** LangChain Deep Agents / OpenClaw (NemoClaw-supported)

**The one architectural insight:** inference is pinned to `inference.local` (operator-chosen, not agent-chosen), so HiddenLayer's security bus and OpenShell's containment boundary converge on the *same* model hop — **one boundary, three tracks.**

---

## What lives here

```
Airtight/
├── README.md                         ← you are here (overview + index)
├── CLAUDE.md                         ← context for Claude Code sessions in this repo
├── docs/
│   ├── ARCHITECTURE.md               ← full spec: concept, layers, FIG.1, 3 claims, model
│   ├── BUILD-PLAN.md                 ← milestones M1–M6, demo script, judge's scorecard
│   └── airtight-spec.html            ← the shareable artifact (patent-spec styled)
└── research/                         ← grounded briefings (verified 2026-07-17)
    ├── hiddenlayer.md                ← AIDR Interactions API: endpoints, payloads, auth, SDK
    ├── nemoclaw-openshell.md         ← blueprint tiers, policy YAML schema, Policy Advisor, CLI
    └── nemotron.md                   ← model lineup + recommendation
```

**Shareable artifact:** https://claude.ai/code/artifact/5ccf4150-8223-4eca-bc0d-2516184a4092

## Status

**Phase: architecture / planning.** Nothing built yet. Next highest-leverage step is the eval-harness ablation (see `docs/BUILD-PLAN.md` → M4) — it's both the Track-1 proof and the best demo moment.
