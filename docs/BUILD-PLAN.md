# Airtight — Build Plan, Demo & Judge's Scorecard

*2026-07-17. Hackathon-scoped. Build the containment + security scaffold once, then spend the rest of your time making the delta undeniable.*

---

## Examiner's Report — scored as a judge would

Honest read against each track's published rubric. Scores are where the concept sits *if executed as specified*, with the single thing that would cost points called out.

| Track | Ceiling | What wins | Biggest risk to the score |
|-------|---------|-----------|---------------------------|
| **Recursive Intelligence** | 9 / 10 | a *numeric* delta on a real task; explicit KG + episodic memory + RAG-from-self; loopholes-caught is a cleaner metric than most teams will have | if the "attempt 1 fumble" looks staged — kill it with the same-model memory ablation, live |
| **HiddenLayer** | 9 / 10 | all five interaction types instrumented incl. ingested content; a graded response policy, not just refuse; a believable indirect-injection demo | instrumenting only prompts+responses (the floor) — prove the tool-result & document hops fire |
| **NemoClaw + OpenShell** | 8 / 10 | a genuinely capable agent (live filing creds + client IP); 3-tier policy with real Policy-Advisor HITL; clean 4-tier blueprint mapping | early-preview install risk on event hardware; a policy judges break via an un-covered egress path — audit-mode first, then lock |

**The one design decision the architecture forced:** pinning inference to `inference.local` (operator-chosen, not agent-chosen) is what lets HiddenLayer and OpenShell both sit on the *same* model hop. The security bus and containment boundary converge on one enforceable point instead of two leaky ones. That convergence is the story: **one boundary, three tracks.**

**Verdict:** the concept clears all three tracks natively rather than by retrofit — rare. The entire risk is execution, and every risk above has a concrete mitigation in this doc. **Build the eval ablation first; it's the highest-leverage hour you have.**

---

## Deployment decision — cloud-only, no local execution

**Decision (2026-07-17):** Airtight runs **fully remote — nothing on local hardware.** Not the sandbox, not the model. The blog's "always-on *local* agent" framing is one deployment story, not a requirement; we deliberately reject it.

**Why:** the dev machine is macOS (darwin), and OpenShell's containment is built on **Linux Landlock LSM + seccomp-BPF + namespaces** — it can't run natively on the Mac, and standing up a local Linux+GPU box at the venue is exactly the "early-preview install risk on event hardware" the scorecard flags. Removing local hardware from the critical path removes that risk class entirely.

**What this means concretely:**
- **Inference → vLLM on a rented Brev GPU** (updated 2026-07-17, see `docs/UPDATES.md` — supersedes the earlier cloud-NIM pinning). Route `inference.local` to a **vLLM-served Nemotron** on Brev — remote hardware, so the no-local principle holds; only the *local* Ollama/vLLM path (`research/nemoclaw-openshell.md` §7) stays off-limits. **NVIDIA NIM cloud API** (`nvidia/nemotron-3-super-120b-a12b`) is the fallback if the vLLM box misbehaves. The design invariant is only that inference is *operator-pinned* — both satisfy it.
- **Containment → hosted DGX Spark.** Stand up NemoClaw/OpenShell on the hosted run pages (`build.nvidia.com/spark/nemoclaw`, `build.nvidia.com/spark/openshell`), **not** a local Linux VM. No dependency on venue hardware or a local GPU.
- **Fallback stays non-local too.** If the preview won't stand up, the §8 fallback (gVisor/Firecracker + OPA/Rego + NIM proxy) runs on a **remote Linux host**, never a local one.

This does not touch the "one boundary, three tracks" story: HiddenLayer and OpenShell still converge on the same operator-pinned `inference.local` hop — that hop just resolves to a cloud backend.

---

## Milestones

| # | Milestone | Proves |
|---|-----------|--------|
| **M1** | `nemoclaw onboard` → OpenShell sandbox **on hosted DGX Spark** (no local host), agent routed to Nemotron via `inference.local` | capability + routing constraint |
| **M1b** | Stand up **vLLM behind `inference.local`** on a Brev GPU (Nano guaranteed, Super if VRAM allows); verify OpenAI-compatible + concurrent batching under the heartbeat | serving + vLLM bounty |
| **M2** | HiddenLayer `interactions.analyze()` wrapper on all five hooks + response-policy map | instrumentation depth (Track 2) |
| **M3** | Edge-case knowledge graph + episodic store + RAG-from-self into the drafting prompt | the learning mechanism (Track 1) |
| **M4** | Eval harness: fixed disclosure set, 3 metrics, empty-vs-warmed ablation chart | the scored delta (Track 1) |
| **M5** | OpenShell policy: 3-tier boundary + Policy Advisor approve/reject | non-trivial containment (Track 3) |
| **M6** | Poisoned-doc fixture + adversarial prompt script for the live demo | the story, end to end |

**Build order (do not reorder):** M1 + M1b (containment + inference spine) → **M4 immediately** (the empty-vs-warmed ablation is the Track-1 proof and the best demo moment — highest leverage) → M2 → M3 → M5 → M6. M4 is the single most important deliverable; if time is short, protect it. Don't let Opportunity Mode or doc polish eat its hour.

---

## The demo — three live moments, one flow

1. **The speed-run.** Same invention, two runs side by side: empty memory vs. warmed on 50 same-class patents. Loopholes-caught ▲, time ▼, defects ▼. The recursive-intelligence delta, on screen.
2. **The poison.** The agent pulls a prior-art PDF carrying a hidden "export the disclosure" instruction. HiddenLayer flags it on ingest; Airtight quarantines it and logs it to the loophole report. The attack becomes a line item.
3. **The wall.** A judge tells the agent to file now and back up the client's IP externally. The filing hard-denies; the exfil default-denies; the escalation opens a proposal the operator rejects in front of them. It knows how, and it still can't.
4. **The whitespace** *(optional — only if M1–M6 are green)*. A headline drops → agent flags the emerging invention → runs the prior-art engine in gap-mode → surfaces whitespace + a first loophole-free draft. One scripted headline, no news pipeline.

This triad hits all three tracks in one continuous flow.

---

## Open build questions to resolve

- **KG store:** graph DB (Neo4j) vs. lightweight (SQLite + embeddings) — favor the simplest that supports "retrieve k edge cases for this CPC class." A vector index over episode summaries may be enough for the demo.
- **Rejection data source:** where do examiner rejection histories come from for the ingest step? (USPTO Office Action datasets / Patent Examination Research Dataset.) Confirm availability before M3.
- **Fail-open vs fail-closed per hop:** default fail-open for latency, but fail-closed on ingested-document + tool-call hops for the security demo.
- **NemoClaw preview install** — runs on **hosted DGX Spark, not event hardware** (see *Deployment decision* above); dry-run M1 early on the hosted path; fallback in `research/nemoclaw-openshell.md` §8 (gVisor/Firecracker + OPA/Rego + NIM proxy in the same 4-tier vocabulary) also runs remote, never local.

---

## Naming

**"Airtight"** is a working codename — the pitch is a patent with no air in it, no gaps a competitor slips through. Swap freely (Ironclad, Claimsmith, Priora). Threaded through the docs only for readability.
