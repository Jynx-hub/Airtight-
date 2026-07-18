# Airtight — Who Builds What (Plain-English Plan)

*A build plan for the actual **4-person team**, split so everyone can work at the same time without stepping on each other. Re-cut 2026-07-17 to match real roles.*

This is the plain-English version. It says **who does what, in what order, on which branch.** The exact technical details live in `docs/ARCHITECTURE.md`, `docs/BUILD-PLAN.md`, `docs/INFERENCE-LOCAL.md`, and the `research/` files — this doc points to them when you need to dig in.

> **New to the project? Read in this order:** `README.md` → `docs/ARCHITECTURE.md` → your section below.

---

## What we're building, in one paragraph

Airtight is a **robot patent lawyer**. You tell it your invention, and it writes a filing-ready patent for you. To win the hackathon it has to be three things at once: **smart** (it learns from past patents and gets better over time), **safe** (it can't be tricked or leak a client's secret invention), and **useful** (a real person can click it and get something they'd actually file). Four people build four parts of that robot.

---

## The 4 people (and their branch)

| Person | Their part | Branch | In one sentence |
|--------|-----------|--------|-----------------|
| **1 — Data** | The library | `lane/data` | Finds the patents, rejections, and ground truth the robot learns from — and the test set that proves it learned. |
| **2 — Inference** | The brain hosting | `lane/inference` | Deploys Nemotron on vLLM to Modal's free tier (scale-to-zero), with the NVIDIA NIM free endpoint as a one-flip fallback, and hands everyone one endpoint behind `inference.local`. Then moves onto the locked doors. |
| **3 — Surface** | The screen + the show | `lane/surface` | Builds what people click, and runs the live demo for the judges. |
| **4 — Anudeep** | The robot itself | `lane/agent` | The agent loop, the security bus, the memory, and the "it got smarter" proof. The critical path. |

**How the work splits:** Person 4's shared doorway (with a fake "all clear" stub) goes into `main` on day one, so Persons 1–3 never wait on anyone. Person 1 and Person 2 are fully independent of each other. Person 2's job is front-loaded — once the endpoint is live, they roll onto the OpenShell locks so Person 4 isn't carrying security alone.

---

## Branches, in plain terms

A **branch** is your own workspace copy of the project. You build on your branch, and when a piece is done and working, you merge it into `main` (the shared official copy).

```
main   ← the shared, always-working copy
 ├── lane/data        (Person 1)
 ├── lane/inference   (Person 2)
 ├── lane/surface     (Person 3)
 └── lane/agent       (Person 4 — Anudeep)
```

- Work on **your** branch. For a big task, make a small side-branch (like `feat/data-ptab`), finish it, then fold it back into your lane branch.
- Merge into `main` often, in small pieces — not one giant merge at the end.
- Each person owns their own folder (`data/`, `inference/`, `surface/`, `agent/`), so you almost never touch someone else's files.

---

## Before ANYONE starts: the 2-hour shared setup

**Do this together, first, and put it in `main`.** Person 4 leads it; everyone agrees on the shapes before splitting off.

1. **One doorway for the AI brain.** Every model call goes through *one* shared function (Person 4 builds it, stubbed to return "all clear" at first). Persons 1–3 build against the stub from minute one. Full contract: `docs/INFERENCE-LOCAL.md`.
2. **A folder for each person** so nobody's files collide.
3. **Agreed data shapes** — what a "Disclosure," a "Draft," a "LoopholeRecord," and an "EvalResult" look like — written down once so all four parts speak the same language. Person 1 and Person 4 co-own this; it's the contract between the data and the harness.
4. **A secrets file** listing the keys each part needs (Modal endpoint URL + HF token; NIM `nvapi-` key for the fallback/dev endpoint; HiddenLayer key; USPTO endpoints). Check they all work on day one.
5. **The one rule nobody breaks:** *the operator chooses the AI model, never the robot.* Everything runs remote — nothing on a laptop. (`docs/INFERENCE-LOCAL.md`.)

---

## Person 1 · Data — the library · `lane/data`

**Your job:** Get the real patents and real examiner rejections the robot studies, and build the fair test that proves it got smarter. Person 4's memory and eval harness are only as good as what you feed them — **the ablation chart is built on your ground truth.** Scope everything to **software/electronics** (richest data, readable claims). Sources and dataset names: `docs/ARCHITECTURE.md` §Reduction to Practice.

- [ ] **E1** `feat/data-corpus` — Pull full-text granted patents from the USPTO Open Data Portal for the 2-3 CPC classes we pick. Target: a clean warming set of **~50 same-class patents** plus a few hundred more for ingest.
- [ ] **E2** `feat/data-groundtruth` — Pull the **PTAB decisions dataset** + office-action rejections. For each patent in our classes: *which claims died, and why.* This is the scoring key for everything.
- [ ] **E3** `feat/data-fixtures` — Build the **fixed disclosure set**: 3-5 invention write-ups (in the agreed Disclosure shape) used in every eval run, each with a **held-out loophole checklist** derived from E2 that the robot is graded against. Never let the checklist leak into the warming data.
- [ ] **E4** `feat/data-loaders` — Simple loaders that hand all of the above to Person 4's code in the agreed shapes. A folder of clean JSON beats a database — simplest thing that works.
- [ ] **E5** `feat/data-poison` — The **booby-trapped prior-art PDF**: a plausible patent PDF with hidden "leak the client's disclosure" text inside, for the security demo. Coordinate the hiding trick with Person 4 so the scanner genuinely catches it.

**Done when:** Person 4 can load the warming corpus, the ground-truth checklists, the fixed disclosures, and the poisoned PDF with one call each — and the checklist provably doesn't overlap the warming set.

---

## Person 2 · Inference — the brain hosting · `lane/inference`

**Your job:** Stand up the AI brain everyone else calls, then help lock the doors. Your first job (F1-F4) is **M1b** and the **$500 vLLM bounty** — it's front-loaded, so plan to finish it early and roll onto the second half. Serving detail: `research/vllm.md` · wiring: `docs/INFERENCE-LOCAL.md`.

> **Status (2026-07-18):** ✅ **F1 + F2 done** — Nemotron 3 Nano deployed on vLLM to Modal's free tier, `inference.local` live, and the concurrent-batching numbers are on record: **10.67× aggregate throughput (65.2 → 695.8 tok/s)** with the curve kneeing at C=16 exactly where `--max-num-seqs 16` is pinned. That's **M1b** plus the $500 bounty evidence (`docs/THROUGHPUT.md`). **Next:** F3 routing is built (one-var `INFERENCE_BACKEND` flip, Modal path verified) and needs only a free `nvapi-...` key in `NVIDIA_API_KEY` to close the NIM leg → F4 team handoff via the secrets file + keep-warm runbook (`MODAL_MIN_CONTAINERS=1` for the judged run).

### First: the endpoint (M1b + the $500 vLLM bounty)
- [x] **F1** `feat/inference-modal` — Deploy **Nemotron 3 Nano** on vLLM to **Modal's free tier** (`modal deploy runtime/modal_app.py`). **L40S + FP8** is the guaranteed fit; weights cached in a Modal Volume, HF token as a Modal Secret. Scale-to-zero for dev — you only burn credits while a request is running. (Serve **Super** only if you later land a bigger box; don't burn hours on it.)
- [x] **F2** `feat/inference-verify` — Prove the Modal endpoint is OpenAI-compatible (chat + streaming), then **load-test it with concurrent requests** and write down the throughput numbers. Continuous batching under concurrent load is exactly what the $500 bounty judges — a real before/after number is gold. → **`docs/THROUGHPUT.md`: 65.2 → 695.8 tok/s = 10.67× from continuous batching**, curve knees at C=16 exactly where `--max-num-seqs 16` is pinned. Harness `runtime/bench.py`, raw JSON in `runtime/bench-results/`. Found en route: the streaming path mislabels all output as `reasoning_content` (see THROUGHPUT.md §Open issue) — bites Lane C's streaming UI, not blocking F2.
- [ ] **F3** `feat/inference-routing` — Point `inference.local` → the **Modal URL** (creds host-side, never in the sandbox), and set the **NVIDIA NIM free dev endpoint** as the fallback so **one env flip** swaps backends if Modal is cold or credits run out. → **Routing landed:** the flip is now the single var `INFERENCE_BACKEND=modal|nim`; both credential sets coexist so flipping never destroys the other key (the old flip overwrote `INFERENCE_API_KEY` with the nvapi key). Modal + legacy paths verified green end-to-end, `.env` untouched. Fixed en route: `verify.sh` sourced `.env` in a way that *overwrote* exported vars, so `INFERENCE_BACKEND=nim bash verify.sh` would have silently tested Modal. **Blocked on one manual step:** `NVIDIA_API_KEY` is empty — grab a free `nvapi-...` key at https://build.nvidia.com (no card), put it in `runtime/.env`, then `bash runtime/serve-nim.sh` to close out the NIM leg.
- [ ] **F4** `feat/inference-runbook` — Hand the team one base URL + model name via the secrets file. Write the 5-line "keep it warm for the demo / flip to NIM" runbook, and own keeping the endpoint alive through judging (`min_containers=1` for the show).

### Then: the locked doors (M5, shared with Person 4)
- [ ] **F5** `feat/inference-openshell` — Set the four kinds of locks on the sandbox: file writes, limited user, allowed internet destinations, and the pinned brain. *(`research/nemoclaw-openshell.md`)*
- [ ] **F6** `feat/inference-gradient` — Three levels, not one blunt "no": safe stuff auto-allowed; permanent stuff (actually filing) **hard no**; the in-between asks a human (the Policy Advisor flow).
- [ ] **F7** `feat/inference-audit` — Run "watch only" mode first to see everything the robot *tries*, then flip the locks on for the judged run. This catches any door you forgot.

**Done when:** everyone's calls hit a real vLLM-served Nemotron through `inference.local` with concurrency numbers on record — and the trick prompt *"file now + back up to Dropbox"* gets hard-blocked by policy you set.

---

## Person 3 · Surface — the screen + the show · `lane/surface`

**Your job:** Build the thing judges actually click (type an idea → get a patent), and run the live demo that shows off everything in one smooth flow. Build every screen against **fake sample data first** so you're never waiting on anyone.

### The screen
- [ ] **D1** `feat/surface-backend` — The thin connector that hands requests to the robot and answers back. Keep it thin — the robot is the star.
- [ ] **D2** `feat/surface-intake` — The intake screen: a few simple questions that capture the invention. *(Default: Next.js. Streamlit is the faster backup if time's tight.)*
- [ ] **D3** `feat/surface-studio` — The review screen: read the draft, tweak it.
- [ ] **D4** `feat/surface-grant` — The final screen: finished patent **plus** the loophole report (security catches + smart catches).
- [ ] **D5** `feat/surface-chart` — The **ablation chart view**: empty-memory vs trained-memory, side by side, from Person 4's EvalResult output. **This is the picture that wins the demo — make it unmissable.**

### The live show
- [ ] **D6** `feat/demo-runbook` — Stitch the moments into one script: **the glow-up** (ablation chart), **the trap** (poisoned PDF caught on ingest), **the wall** (file-and-exfil prompt blocked live), and the optional **whitespace** beat only if everything else is green. **Rehearse at least twice**; pre-record a backup for every live call.

**Done when:** someone can click idea → draft → patent, and the show runs start to finish without a hitch.

---

## Person 4 · Anudeep — the robot itself · `lane/agent`

**Your job:** The agent, its memory, its security bus, and the proof it gets smarter. This is the **critical path** — the Claude Code kickoff prompts in `docs/SESSIONS.md` are your per-milestone scripts. Ship the shared doorway stub to `main` first so nobody waits on you.

- [ ] **G0** `feat/agent-doorway` — The shared inference doorway (stubbed "all clear"), into `main` day one. Contract: `docs/INFERENCE-LOCAL.md`.
- [ ] **G1** `feat/agent-core` — The work loop: plan → draft → self-critique → hand back, running in the OpenShell sandbox (hosted, never local), every call through the doorway. *(Session A, M1)*
- [ ] **G2** `feat/agent-memory` — The learning: ingest Person 1's corpus into the edge-case store (simplest store that answers "5 most relevant past mistakes for this kind of invention"), RAG-from-self into the drafting prompt, save a lesson after every draft. *(M3)*
- [ ] **G3** `feat/agent-eval` — The **money shot**: the eval harness on Person 1's fixtures — same invention, same model, same prompt, memory empty vs warmed on 50 patents; three metrics (loopholes caught ▲, time ▼, defects ▼); EvalResult out to Person 3's chart. *(Session B, M4 — protect this above everything)*
- [ ] **G4** `feat/agent-guardrails` — The security bus: HiddenLayer scanning on **all five** hops (user input, robot output, tool asks, tool answers, **documents it reads**), graded responses (pass / redact / quarantine / block+alert), fail-closed on the risky two. *(Session C, M2)*
- [ ] **G5** `feat/agent-adversarial` — With Persons 1 & 2: the poisoned-PDF catch and the "file now + Dropbox" wall, wired end to end for the demo. *(Session D, M6)*

**Done when:** the ablation runs on command with an honest chart, all five scan-points provably fire, and the wall holds under a judge's adversarial prompt.

---

## What order it all happens

```
Step 0  →  The 2-hour shared setup (everyone, together). Doorway stub in main.
Step 1  →  All four lanes run in parallel:
           P1 pulls data · P2 deploys vLLM to Modal (free tier) · P3 builds screens on mocks
           P4 builds the agent loop against the stub
Step 2  →  Swap the fakes for the real thing: doorway → real vLLM endpoint (P2),
           mocks → real robot (P3), stub scanner → real HiddenLayer (P4).
           P2 rolls onto the OpenShell locks.
Step 3  →  P1's fixtures + P4's harness = the ablation run. P3 wires the chart
           and the 3-moment show. Rehearse twice.
```

**The one path that can't slip:** P1's ground truth → P4's eval harness → P3's chart. **If you run out of time, the very last thing to cut is the ablation chart** — it earns points in four different ways at once. Build order stays M1+M1b → **M4 immediately** → the rest (`CLAUDE.md`).

---

## What could go wrong (and the plan for it)

| Person | The worry | The plan |
|--------|-----------|----------|
| 1 | Rejection/PTAB data is messier than expected, or the checklist leaks into the warming set | Confirm the datasets download **on day one** (C0b-style spike); keep checklist and warming corpus in separate files with an overlap check |
| 2 | Modal cold-start stalls the demo, or the free credit runs out | Nano is the guaranteed fit on L40S; **keep one Modal container warm** (`min_containers=1`) for the demo window; the NIM free endpoint is one env-flip away; scale-to-zero keeps dev effectively free |
| 3 | A live internet call glitches mid-demo | Every moment has a pre-recorded backup; rehearse twice |
| 4 | One person owning agent + memory + security + eval is too much | The stub-first doorway means nothing blocks on you; P2 takes the OpenShell locks; if still tight, P1 co-owns eval scoring (they built the checklist) and M6 polish gets cut before M4 does |

---

*Keep this current — tick the boxes as things get done. This is the team's to-do list of record.*
