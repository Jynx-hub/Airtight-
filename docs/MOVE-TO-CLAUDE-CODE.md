# Airtight → Claude Code: Handoff Kit

Everything to go from the planning repo to building in Claude Code. Do it in order. Keep this file at `docs/MOVE-TO-CLAUDE-CODE.md`.

---

## 0. Prereqs

- A terminal, git, and a GPU box for vLLM (Brev — you have $100/team-member credits).
- Node 22+ *only if* you install via npm. Otherwise use the native installer (no Node needed).

## 1. Install Claude Code

**Native installer (recommended, no Node):** grab it from <https://code.claude.com>.

**Or npm:**
```bash
npm install -g @anthropic-ai/claude-code
# upgrade later: npm install -g @anthropic-ai/claude-code@latest
```

## 2. Authenticate

```bash
claude
```
A browser opens for login (press `c` to copy the URL if it doesn't). Log in with your Claude subscription, or an API key from the Claude Console. Credentials are stored in the macOS Keychain or `~/.claude/.credentials.json`.

## 3. Clone the repo and drop in the new files

```bash
git clone https://github.com/Jynx-hub/Airtight-.git
cd Airtight-
# add the two files from the planning session:
#   research/vllm.md
#   docs/UPDATES.md
git add research/vllm.md docs/UPDATES.md
git commit -m "Add vLLM briefing + plan updates"
```
Then apply the small edits listed in `docs/UPDATES.md` (vLLM track row, Opportunity Mode subsection, M1b milestone) and commit.

## 4. Start Claude Code in the repo

```bash
claude
```
The repo already has a `CLAUDE.md`, which Claude Code reads automatically at the start of every session — so it starts with full project context. If you want it refreshed against the current tree, run `/init` (regenerates a starter CLAUDE.md) and trim with `/doctor`. Keep CLAUDE.md under ~200 lines; it loads into context on every request.

**One thing to add to CLAUDE.md** (a "build order" rule so any session knows the priority):
```
## Build order (do not reorder)
1. M1 + M1b: OpenShell sandbox + agent routed to a vLLM-served Nemotron via inference.local
2. M4: empty-vs-warmed ablation harness (Track-1 proof + best demo) — highest leverage
3. M2 HiddenLayer hooks · M3 knowledge graph/RAG-from-self · M5 policy · M6 adversarial fixtures
Benchmark stays on loophole-finding (PTAB ground truth). Opportunity/whitespace mode is a demo funnel, not the benchmark.
```

---

## 5. Working style (first-session best practices)

- **One milestone per session.** Use `/clear` between milestones — don't mix M1 and M4 in one context.
- **Plan before building.** Enter plan mode with `/plan` for each milestone; review the plan, then approve to execute. It inspects and plans without editing files first.
- **Let it use subagents** for parallel work (e.g., one drafts the eval harness while another wires the sandbox).

---

## 6. Copy-paste kickoff prompts

Paste these one at a time, each in its own session (`/clear` between).

### Session A — scaffold + M1/M1b (plan first)
```
/plan
Read CLAUDE.md, docs/ARCHITECTURE.md, docs/BUILD-PLAN.md, docs/UPDATES.md, and research/vllm.md, research/nemoclaw-openshell.md, research/nemotron.md.

Goal for this session: M1 + M1b. Scaffold a src/ layout and stand up the containment + inference spine:
- OpenShell sandbox via NemoClaw, harness = LangChain Deep Agents / OpenClaw.
- Agent inference pinned to inference.local, which forwards to a vLLM-served Nemotron (start with Nemotron 3 Nano for reliability; Super if the GPU allows).
- Verify the OpenAI-compatible endpoint works and handles concurrent requests (continuous batching).

Give me a plan with the exact files you'll create, the vllm serve command, and the inference.local wiring. Don't edit yet — plan first, flag any repo paths or CLI verbs that need confirming against the early-preview NemoClaw/OpenShell docs.
```

### Session B — M4 the ablation harness (the money milestone)
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

### Session C — M2 HiddenLayer instrumentation
```
/plan
Read research/hiddenlayer.md and docs/ARCHITECTURE.md (Claim 2).

Wrap ALL FIVE interaction types through HiddenLayer AIDR interactions.analyze(): user prompt, model response, tool call args, tool result, and ingested document. Implement the graded response-policy map (pass / redact / quarantine / block+escalate). Run fail-closed on the ingested-document and tool-call hops. Then build the poisoned-prior-art-PDF fixture (M6) so the demo shows detection on ingest.
```

### Session D — M5 OpenShell policy + M6 adversarial fixtures
```
/plan
Read research/nemoclaw-openshell.md and docs/ARCHITECTURE.md (Claim 3).

Author the three-tier OpenShell policy: reversible auto-allow, irreversible hard-deny (filing POST), ambiguous → Policy Advisor HITL. Datastore read-only, no external egress of disclosure bytes. Start enforcement: audit to capture the real egress set, then flip to enforce. Then write the adversarial demo script ("file now + back up to Dropbox") that proves the wall holds.
```

---

## 7. Optional: a custom slash command for the eval

Create `.claude/commands/ablation.md`:
```
Run the M4 ablation: empty vs warmed knowledge graph on the fixed disclosure set. Report loopholes-caught, drafting time, and correctness for both, and render the side-by-side chart. Same model, same prompt — only the retrieved memory differs.
```
Then just type `/ablation` in any session to re-run it.

## 8. MCP servers (only if you need them)

You don't need MCP for the core build (HiddenLayer and vLLM are plain HTTP APIs your code calls). If you later want a patent-data source or tracker as a tool:
```bash
claude mcp add --transport http <name> <url> --scope project
```
`--scope project` shares it with teammates via the repo. Manage with `/mcp` inside a session.

---

## The one thing not to lose

Build M1+M1b, then **M4 immediately**. The ablation is your Track-1 proof and your best demo moment. Everything else is supporting cast. Don't let Opportunity Mode or doc polish eat that hour.
