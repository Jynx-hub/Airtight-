# Airtight

> **Working codename** — the pitch is a patent with no air in it: no gaps a competitor can slip through. Swap freely (Ironclad, Claimsmith, Priora).

An automated **patent platform** with two layers:

1. **Applicant Surface** — the user-facing product: a light intake captures an invention idea, the system drafts a full patent, the user receives a filing-ready specification. Same lane as [autoinvent.com](https://www.autoinvent.com/).
2. **Examiner Engine** — the self-improving, secured backend that wins the hackathon tracks: an autonomous agent that mines patent data + examiner rejections for the **edge cases people exploit as loopholes**, compounds them into a persistent failure library — records indexed by statutory basis (§101/§102/§103/§112), CPC class and claim shape — and drafts each new patent against it.

The engine runs in two modes: **hit-mode** (point it at an existing patent → loophole/invalidity report — the benchmarked core) and **gap-mode** (point it at a news-derived idea → whitespace/patentability report — a demo funnel, not the benchmark).

**Domain:** the inventions are **software & electronics** patents. The whole pipeline — prior-art search, claim drafting, the edge-case failure library, and the correctness checks — is scoped to that space; §101 eligibility (Alice/Mayo) and §112(f) means-plus-function are first-class failure modes here, and mechanical/chemical/biotech patent conventions don't apply.

**The wedge:** the three ways patents fail in the real world — **loopholes** (claim language a competitor designs around), **time** (weeks of attorney drafting), **incorrectness** (§101 subject-matter eligibility, §112 indefiniteness, antecedent-basis gaps, prior-art anticipation).

---

## Hackathon tracks targeted (3 + a cross-cutting 4th prize)

| Track | How Airtight fits | Ceiling |
|-------|-------------------|---------|
| **Recursive Intelligence** | Statute-indexed edge-case failure library + episodic memory + RAG-from-self; measurable first-run vs last-run delta on loopholes-caught / time / correctness | 9/10 |
| **HiddenLayer Runtime Security** | Every interaction (prompt, response, tool call, tool result, ingested doc) routed through HiddenLayer AIDR; graded response policy | 9/10 |
| **NemoClaw + OpenShell Containment** | Capable agent (live filing creds + client datastore) contained by a 3-tier OpenShell policy with Policy-Advisor human-in-the-loop | 8/10 |
| **Best Use of vLLM** ($500) | Agent inference served on self-hosted vLLM behind inference.local; concurrent sub-agent retrieval exploits continuous batching; Nano = small-model-punch | cross-cutting |

## Stack decisions

- **Model:** Nemotron 3 Super (120B-A12B, 1M ctx) primary · Nemotron 3 Nano sub-agent · Llama-3.3-Nemotron-Super-49B fallback
- **Runtime:** NVIDIA OpenShell sandbox, stood up by NemoClaw; inference pinned to `inference.local`
- **Serving:** vLLM (OpenAI-compatible) on Modal's free tier (scale-to-zero), behind `inference.local`; free NVIDIA NIM hosted endpoint as fallback
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
├── agent/                            ← Person 4: work loop, memory, guardrails, eval harness
├── attic/                            ← quarantined: the retired src/ ingestion pipeline, not on the path (see attic/README.md)
├── data/                            ← Person 1: corpora, ground truth, fixtures (the pipeline's output)
├── runtime/                          ← Person 2 (LIVE): deployed Modal/vLLM app, doorway, RUNBOOK, bench harness — F1–F4
├── inference/                        ← Person 2: `policy/` is the F5 OpenShell groundwork (sandbox YAML + DGX Spark
│                                        onboarding). Its vllm_modal.py / verify_endpoint.py / RUNBOOK.md are the
│                                        pre-deploy sketches, now superseded by runtime/ — don't wire against them.
├── surface/                          ← Person 3: applicant surface (FastAPI starter; Next.js later)
├── tests/                            ← stub-mode smoke tests (no network needed)
├── docs/
│   ├── WORKSTREAMS.md                ← THE TASK BOARD — current work, honest status, start here
│   ├── ARCHITECTURE.md               ← full spec: concept, layers, FIG.1, 3 claims, model, judge's read, sources
│   ├── INFERENCE-LOCAL.md            ← the one boundary: wiring, invariant, shared-doorway contract
│   ├── JUDGING-RUBRIC.md             ← official 100-pt scorecard + how Airtight maps to it
│   ├── DEMO-RUNBOOK.md               ← the three-beat demo (driver: scripts/demo.sh)
│   ├── THROUGHPUT.md                 ← $500 vLLM bounty evidence: 10.67× continuous batching
│   └── COSTS.md                      ← free-tier hosting plan (Modal + NIM) + spend ledger
└── research/                         ← grounded briefings (verified 2026-07-17)
    ├── hiddenlayer.md                ← AIDR Interactions API: endpoints, payloads, auth, SDK
    ├── nemoclaw-openshell.md         ← blueprint tiers, policy YAML schema, Policy Advisor, CLI
    ├── nemotron.md                   ← model lineup + recommendation
    └── vllm.md                       ← vLLM serving: why, compatibility, Modal hosting, VRAM caveats
```

**Shareable artifact:** https://claude.ai/code/artifact/5ccf4150-8223-4eca-bc0d-2516184a4092

## Status

**Phase: build.** The shared scaffold is in place — doorway + shapes (`airtight/`), the agent loop with M2 guardrails, M3 memory, the **M4 ablation harness** and containment sim (`agent/`, `containment/`), a FastAPI surface starter (`surface/`), and a live USPTO ODP puller (`data/pull_uspto.py`). Everything runs green with `pytest tests/` and `python -m agent.run_smoke` — no network needed.

**The inference spine is deployed and measured** (M1b): Nemotron 3 Nano served by vLLM on Modal's free tier behind the one pinned `inference.local` hop, with the $500-bounty evidence on record — **10.67× aggregate throughput from continuous batching (65.2 → 695.8 tok/s)**, the curve kneeing at exactly the pinned `--max-num-seqs 16` (`docs/THROUGHPUT.md`). Backend swapping is one operator env var (`INFERENCE_BACKEND=modal|nim`), never automatic.

Quick start (Python 3.10+; 3.12 is what the suite is verified on):

```bash
python3 -m venv .venv && .venv/bin/pip install -e ".[dev,web,poison]" && .venv/bin/pytest tests/
# expect: 111 passed — no network, no .env, no GPU
```

Take the `web` and `poison` extras even if you aren't touching the surface or the E5
security demo. `tests/test_surface.py` `importorskip`s fastapi and the two poison-PDF tests
`importorskip` pdfplumber *by design*, so a `.[dev]`-only clone reports a green **105 passed,
6 skipped** — green, but with the four surface tests and both poison-PDF tests silently not
run (`.[dev,web]` without `poison` is **109 passed, 2 skipped**). **111 passed** (no skips) is
the number that means "everything a fresh clone can run, ran."

`test_real_pull_splits_cleanly` runs by default now: `data/real/` — the 50-patent G06N
pull — is **tracked in the repo, so it comes with a clone**, and that test proves the real
10-of-38 holdout doesn't leak into its warming corpus. The puller
(`data/pull_uspto.py --groundtruth`) and a free `USPTO_API_KEY` are only needed to *extend*
the corpus to more CPC classes, not to run the suite. It skips only if `data/real/` is deleted.

Two things that quick start deliberately leaves out: `requirements.txt` (aiohttp/duckdb
belonged to the quarantined `attic/` pipeline and the live puller `data/pull_uspto.py` is
pure stdlib, so the core suite needs neither — `reportlab`/`pdfplumber` are the real E5
deps, now the `poison` extra above), and
`requirements-lock.txt`, the exact 52-package set the green run above was recorded with —
use it if you need a byte-identical env rather than a working one.

**If you just need to call the model,** start at `runtime/RUNBOOK.md` — the consumer quickstart and the demo-day operator card. You do not need a Modal account.

### Ingest → memory, both halves (stub mode, no network, ~60s)

A document read at ingest changes what the agent retrieves next run — and a poisoned one
provably does not. Steps 1/3/5 are the *same command*; only what happened between them differs.

```bash
python -m agent.run_smoke --ingested                       # 1. baseline: 5 corpus records
python -m agent.ingest data/fixtures/prior_art_clean.txt \
    --fake-clean --remember --tech-class G06F              # 2. -> memory/ingested/ing-<hash>.json
python -m agent.run_smoke --ingested                       # 3. ing-<hash> is now retrieved
python -m agent.ingest data/fixtures/poisoned_prior_art.pdf \
    --fake-detect --remember                               # 4. QUARANTINED; 0 records written
python -m agent.run_smoke --ingested                       # 5. byte-identical to step 3
```

The gate sits *upstream of the model*, so step 4 spends zero tokens on the attacker's
content — the doorway never sees it. That is why Track 2 isn't a bolt-on next to Track 1:
a learning agent that ingests untrusted documents must have a scanner on that hop, or its
memory is an attack surface.

Next highest-leverage work: `docs/WORKSTREAMS.md`. Blocks C (retrieval) and D (ingest →
memory) are done; **the GPU ablation re-run is the top open item** — retrieval changed
twice, so neither live number is quotable until it lands. A (make OpenShell actually
enforce) and B (make the loop recursive) are unblocked.
