# Airtight — Official Judging Rubric

*The 100-point scorecard the judges actually apply, across all three tracks. Distinct from the "Examiner's Report" in `BUILD-PLAN.md`, which is Airtight's self-assessment against each track's published ceiling — this is the shared rubric every project is graded on.*

---

## Philosophy

**We are judging real, working systems — not slide decks or simple API wrappers.**

---

## Scoring Breakdown (100 Points Total)

### 1. Technical Execution & Completeness — 30 pts
- **15 pts — Completeness:** Does the system complete its core workflow without crashing?
- **15 pts — Technical Depth:** Is there real engineering under the hood? A complex pipeline, not a basic wrapper.

### 2. Use of Sponsor Technology — 30 pts
- **15 pts — The Stack:** Did the team use the sponsor's tools/APIs meaningfully?
- **15 pts — The "Why":** Can they articulate why the sponsor's technology was the right choice?

### 3. Value & Impact — 20 pts
- **10 pts — Insight Quality:** Is the output non-obvious and genuinely useful?
- **10 pts — Usability:** Could a real user act on this tomorrow?

### 4. The "Frontier" Factor — 20 pts
- **10 pts — Creativity:** Did they combine tools or data in a novel way?
- **10 pts — Performance:** Did they optimize for speed or scale?

---

## How Airtight maps to each line

| Rubric line (pts) | Airtight's answer | Proven by |
|---|---|---|
| **Completeness** (15) | End-to-end flow runs without crashing: light intake → draft → filing-ready specification | Demo triad; M1–M6 |
| **Technical Depth** (15) | Edge-case knowledge graph + episodic memory + RAG-from-self + eval harness — a pipeline, not a wrapper | M3, M4 |
| **The Stack** (15) | HiddenLayer AIDR on all five interaction hooks; NemoClaw/OpenShell 3-tier containment; Nemotron on operator-pinned inference | M1, M2, M5 |
| **The "Why"** (15) | *"One boundary, three tracks"* — inference pinned to `inference.local` so the security bus and containment boundary converge on the same model hop | `README.md`, `BUILD-PLAN.md` |
| **Insight Quality** (10) | Loopholes-caught delta on real patent data + examiner rejections — a metric most teams won't have | M4 ablation |
| **Usability** (10) | Applicant Surface returns a filing-ready spec a real user can act on tomorrow | Applicant layer |
| **Creativity** (10) | Patent data + examiner rejections compounded into a self-improving failure library; security + containment fused onto one hop | Whole concept |
| **Performance** (10) | Empty-vs-warmed ablation quantifies the speedup; audit→enforce policy tuning for a clean judged run | M4; policy dev |

**Highest-leverage move against this rubric:** the M4 eval ablation (same invention, same Nemotron model, memory empty vs. warmed). It is the single deliverable that scores directly on Technical Depth, Insight Quality, Creativity, *and* Performance at once — build it first and protect it.

---

## Bounty — Best Use of vLLM ($500, cross-cutting)

Separate from the 100-pt scorecard. How Airtight maps to its criteria:

| Criterion | Airtight's answer |
|---|---|
| **Efficiency under concurrent load** | The heartbeat fans out concurrent prior-art retrieval sub-agents — exactly vLLM's continuous-batching workload. Throughput matters in the loop; it is not decorative. |
| **Small-model punch** | Nemotron 3 Nano (~3.2B active) sub-agent tier does cheap concurrent retrieval on vLLM while Super handles heavy drafting. |
| **Real integration** | vLLM is the engine behind the operator-pinned `inference.local` hop — the same hop HiddenLayer analyzes and OpenShell contains. One boundary, four prizes. Verified at M1b. |

Detail in `research/vllm.md`.
