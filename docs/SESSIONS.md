# Session kickoff prompts

One milestone per Claude Code session; `/clear` between. Plan first (`/plan`), review, then execute. Paste one block per session.

## Session A — scaffold + M1/M1b

```
/plan
Read CLAUDE.md, docs/ARCHITECTURE.md, docs/BUILD-PLAN.md, docs/INFERENCE-LOCAL.md, and research/vllm.md, research/nemoclaw-openshell.md, research/nemotron.md.

Goal for this session: M1 + M1b. Scaffold a src/ layout and stand up the containment + inference spine:
- OpenShell sandbox via NemoClaw, harness = LangChain Deep Agents / OpenClaw.
- Agent inference pinned to inference.local, which forwards to a vLLM-served Nemotron (start with Nemotron 3 Nano for reliability; Super if the GPU allows).
- Verify the OpenAI-compatible endpoint works and handles concurrent requests (continuous batching).

Give me a plan with the exact files you'll create, the vllm serve command, and the inference.local wiring. Don't edit yet — plan first, flag any repo paths or CLI verbs that need confirming against the early-preview NemoClaw/OpenShell docs.
```

## Session B — M4 the ablation harness (the money milestone)

```
/plan
Read docs/BUILD-PLAN.md (M4) and docs/ARCHITECTURE.md (Claim 1).

Build the eval harness that proves recursive improvement:
- Fixed disclosure set (software/electronics), fixed model, fixed prompt scaffold.
- Two conditions: knowledge graph EMPTY vs WARMED on ~50 same-class patents (warm it from PTAB decisions + office-action rejections as ground truth).
- Three metrics: loopholes-caught (vs held-out checklist), drafting time, claim-correctness (§112/§102/§103 via an LLM-judge rubric).
- Output a side-by-side chart of empty vs warmed.

This is the demo centerpiece, so make the delta reproducible and hard to dismiss as prompt luck. Plan the data loading first (USPTO Open Data Portal / PTAB dataset), then the harness.
```

## Session C — M2 HiddenLayer instrumentation

```
/plan
Read research/hiddenlayer.md and docs/ARCHITECTURE.md (Claim 2).

Wrap ALL FIVE interaction types through HiddenLayer AIDR interactions.analyze(): user prompt, model response, tool call args, tool result, and ingested document. Implement the graded response-policy map (pass / redact / quarantine / block+escalate). Run fail-closed on the ingested-document and tool-call hops. Then build the poisoned-prior-art-PDF fixture (M6) so the demo shows detection on ingest.
```

## Session D — M5 OpenShell policy + M6 adversarial fixtures

```
/plan
Read research/nemoclaw-openshell.md and docs/ARCHITECTURE.md (Claim 3).

Author the three-tier OpenShell policy: reversible auto-allow, irreversible hard-deny (filing POST), ambiguous → Policy Advisor HITL. Datastore read-only, no external egress of disclosure bytes. Start enforcement: audit to capture the real egress set, then flip to enforce. Then write the adversarial demo script ("file now + back up to Dropbox") that proves the wall holds.
```

## Re-running the eval

`/ablation` (defined in `.claude/commands/ablation.md`) re-runs the M4 empty-vs-warmed comparison in any session.
