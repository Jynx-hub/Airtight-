# Airtight — Workstreams

The task board of record. Audited against the code on **2026-07-18**.

**Notation.** `[x]` = verified working (observed, not reported) · `[ ]` = not started ·
`◐` = real code exists but the item's defining requirement is unmet.
Never promote a box on the strength of code existing or tests passing.

**Read first:** `README.md` → `docs/ARCHITECTURE.md` → the block you're working.
Ground truth on the tools is in `research/` — read it before writing integration code.
What's canonical vs superseded after the lane merges: `docs/INTEGRATION-STATUS.md`.

---

## Where we are

| Lane | State | One-line reality |
|---|---|---|
| **Data** | ✅ done | 134 patents (G06N/G06F/H04L), 94 held-out checklists, 193 real office-action defects, tracked in git |
| **Inference** | ✅ first half | Nemotron on vLLM/Modal, `INFERENCE_BACKEND=modal\|nim`, 10.67× batching on record |
| **Agent** | ◐ built, shallow | loop + guardrails + eval harness all real and tested; memory is static RAG, nothing compounds |
| **Containment** | ⚠️ simulated | `policy.py` decision logic is real, and now so is an escalation client — but enforcement is still a `print()`. No OpenShell exists |
| **Surface** | ◐ starter | idea → draft → patent works; edit boxes discard input; no chart view |

Suite: `.venv/bin/pytest tests/` → **70 passed**, 0 skipped, stub mode, no network.

**The two headline numbers, stated honestly:**

- **$500 vLLM bounty — solid.** 65.2 → 695.8 tok/s, 10.67× from continuous batching,
  curve kneeing at the pinned `--max-num-seqs 16`. Evidence: `docs/THROUGHPUT.md`.
- **Track-1 ablation — real but not reproducible.** The completed 6-disclosure live run
  (`results/ablation/20260718-122807/`) has warmed beating empty on **5 of 6** disclosures,
  **5/36 → 20/36** loopholes caught. But it ran on `--data-root data/real-eval` with
  `corpus_size: 17`, and **`data/real-eval/` no longer exists in the tree** — so the
  headline cannot currently be re-derived. The pooled layout over the real 193-record
  corpus has never produced a `results.json`. Treat the 5/6 as a real result on a
  deleted input, not as a reproducible claim. Time deltas from that run are not usable:
  the aggregate 348.8s → 126.4s is one 257.8s outlier on the empty arm.

  The two live runs also **disagree, on different corpora** — the distilled-FWD run above
  warmed 5/6, while the salvaged office-action pairs
  (`results/ablation/20260718-100851/transcripts/`) ran backwards 4/10 → 1/10. That is
  exactly what a statute-blind ranker produces, and **that ranker is now fixed** (C1,
  `d1c60b1`, offline-validated). What has *not* happened is the re-measurement: neither
  corpus has been re-run against the fixed retrieval, so both numbers above were produced
  by code that no longer exists. **Neither belongs on a slide until the GPU re-run lands** —
  the retrieval is sound, the measurement is the last step.

---

## The focus now

Four blocks, in dependency order. **A3, B, C and D are all unblocked and can start today** —
only A1/A2/A4/A5 wait on hosted hardware.

### A · Containment — make OpenShell real

Today: `containment/policy.py` is a genuine, data-driven, tested policy evaluator, and
everything around it is theatre. `containment/openshell_sim.py:5-6` says so in its own
docstring. Every "403" is a `print()` (`:29`, `:36`). `attempt_egress()` never opens a
socket. No `openshell` or `nemoclaw` binary is installed anywhere — every occurrence in
the repo is prose or an f-string.

- [ ] **A1 · Stand up the sandbox.** `nemoclaw onboard` on **hosted DGX Spark**, then
  `nemoclaw <name> connect`. Binary go/no-go; gates A2, A4, A5 and the sandbox half of B.
  Steps (all CLI verbs still UNVERIFIED): `inference/policy/ONBOARDING.md`.
  Fallback if the preview won't stand up: `research/nemoclaw-openshell.md` §8
  (gVisor/Firecracker + OPA/Rego + a NIM proxy) on a **remote** Linux host — never local,
  never venue hardware. OpenShell needs Linux Landlock + seccomp-BPF; macOS cannot run it.
- [ ] **A2 · Make the policy YAML enforce.** `inference/policy/airtight-sandbox.yaml`
  covers all four tiers on paper but **ships `enforcement: audit` on every endpoint**
  (`:26,37,43,49,61,75`) — which per `research/nemoclaw-openshell.md` §5 *logs and lets
  traffic through*. The strictness only exists as a Python default arg
  (`containment/policy.py:63`), so the simulator is stricter than the artifact it models.
  Needed: `enforce` on the inference endpoint, **two** inference destinations (Modal *and*
  NIM, not one), and validation against the live schema.
- [ ] **A3 · Wire the Policy Advisor client in — the unblocked one.** The client itself now
  **exists and is tested**: `agent/policy_advisor.py` (landed `0878a5f`) turns a default-deny
  into a narrow `addRule` proposal, blocks on the operator's decision, and refuses to
  escalate a `HARD_DENY` — against an injectable transport that is a mock today and
  `policy.local` when A1 lands. Four tests cover it.
  **But nothing calls it.** `grep -rn policy_advisor` returns its own test and one f-string;
  `containment/demo.py` still runs the nine hardcoded prints in `openshell_sim.py:40-49`,
  with a **pre-written rejection** and no approve path. The escalation logic is a library,
  not a path the demo executes. The remaining work is the wiring: replace `proposal_flow()`
  with a real `PolicyAdvisorClient.escalate()` call, and exercise `MockTransport(approve=True)`
  so both branches are demonstrable. Still does not need A1.
- [ ] **A4 · Close the two honest gaps** (both recorded in `docs/INFERENCE-LOCAL.md`):
  `inference.local` becomes a resolvable host with a gateway process instead of a naming
  contract, and **credentials move host-side** — today `runtime/inference_local.py` reads
  the API key from inside the sandbox, so "creds never in the sandbox" is currently false.
  The gateway injection is the real engineering here, not the YAML.
- [ ] **A5 · Audit → enforce sweep.** Run the full agent under `enforcement: audit`,
  read what it actually tries (`openshell logs <name> --tail --source sandbox`), then flip
  to `enforce`. This is the pass that catches the door nobody thought of — an un-covered
  egress path is the named top risk on this track. Needs a runnable agent, so schedule after B.
- [ ] **A6 · Fix the dead M2 fusion.** `containment/demo.py:11-12` claims the demo fuses
  OpenShell and HiddenLayer on one action — "the one boundary story". It doesn't: the
  `@g.guarded_tool` block at `:36-45` is only reachable on `Decision.ALLOW`, and both
  `attempt_egress` calls return on deny before reaching it. Beat 3 (`:61`) bypasses it
  entirely. **The headline claim of that file is unreachable code at runtime.** Also
  `containment/fixtures/exfil_request.json` is read by nothing.

**Done when:** the trick prompt *"file now + back up to Dropbox"* is blocked by policy the
operator set — filing by `deny_rules`, Dropbox by un-allowlisted egress — with a real 403,
and a proposal the operator can actually approve *or* reject.

### B · Recursion — make the loop compound

Today the loop is a straight line and nothing carries across runs. This is the Track-1
mechanism, and it is the largest gap between what `docs/ARCHITECTURE.md:105-110` claims
and what the code does.

- [ ] **B1 · Add a revise turn.** `agent/loop.py` is three sequential calls — plan (`:81`),
  draft (`:82-87`), critique (`:88`) — and then stops. The critique lands in
  `Draft.critique_notes` (`:94`) and is **never fed back**. `Draft.specification` (`:93`)
  is even set to the raw *pre-critique* text. A hostile examiner finds defects and the run
  ends with those defects still in the draft. Feed the critique back as a revision turn,
  loop until no new findings or N rounds. ~10 lines, and it is the difference between
  "self-critique" and self-*correction*.
- [ ] **B2 · Turn episodic memory on.** `airtight/config.py:37` defines
  `EPISODES_ENABLED` — and **it is referenced nowhere else in the repo**. Setting
  `AIRTIGHT_EPISODES_ENABLED=true` changes nothing. The real gate is the `--episodes` CLI
  flag (`agent/run_smoke.py:24`) and the `episode_sink=None` default (`agent/loop.py:60`),
  which the eval harness never passes (`agent/eval/harness.py:181`). `memory/episodes/`
  holds one 0-byte `.gitkeep`; **no episode has ever been written.** Consequence worth
  saying out loud: the measured ablation contains zero compounding — it measures static
  RAG only.
- [ ] **B3 · Bound the distillation before switching it on.** `compress_run`
  (`agent/episodes.py:49-59`) appends **one synthetic `LoopholeRecord` per line of
  `critique_notes`**, and `critique_notes` is every non-blank line of the reply
  (`agent/loop.py:94`) — so markdown headers and "Here are the defects:" become
  first-class memory records that re-enter retrieval. Combined with C2's unnormalized
  ranking, self-generated noise outranks real PTAB records within a few runs. **Do B3
  before B2 ships**, or compounding poisons its own corpus.

Two smaller correctness items in the same area: `EpisodeStore.load` uses `rglob`
(`agent/episodes.py:84`) while `LoopholeStore.load` uses `glob` (`agent/memory.py:31`) —
the two stores disagree on recursion. And `.gitignore` ignores `memory/episodes/*.json`
while `record()` writes to `memory/episodes/<disclosure_id>/*.json`, so the first episodes
ever written get staged despite the stated intent.

### C · Context memory — make retrieval right

`agent/memory.py` ranks on a 3-tuple: `technology_class` exact match, raw token overlap,
then `rec.id` reverse-alphabetical (`:41-48`). The store is a plain Python list hydrated
from a flat JSON directory (`:25`, `:29-35`) — no index, no embeddings.

- [x] **C1 · Rank by statute — done 2026-07-18 (`d1c60b1`), offline-validated.**
  `LoopholeRecord` now carries a `statute` field (`airtight/shapes.py`), derived from the
  pattern text by a model validator so the 193 existing records need no re-pull, and
  `retrieve()` spreads the k across §101/§102/§103/§112 via `diversify_by_statute`
  (`agent/memory.py`) instead of collapsing onto whichever statute won on keyword overlap.
  `agent/episodes.py` delegates to the same function, so the episodic and warming paths
  rank identically. Three tests cover derivation, spread and determinism.
  **The fix is diversification, not the statute-*matching* this item originally proposed —
  and the correction matters.** `Disclosure` has no statute field; a disclosure's statute is
  only knowable from its held-out checklist, so ranking to match it would have leaked the
  graded answer into the warmed arm and the leakage guard should have caught it. Spreading
  the k gets the coverage without the leak.
  Validated on the real corpus: all 6 graded disclosures now retrieve a statute set that
  **includes their checklist's statutes**, where before they collapsed onto one — the
  mechanism behind the backwards run.
  **What's left is measurement, not code:** neither corpus has been re-run live, so the
  delta itself is still unproven. Tracked as a risk below.
- [ ] **C2 · Normalize the overlap score.** Overlap is a raw unnormalized count against
  `pattern + claim_shape + remedy`, and real records carry 600+ char `claim_shape` fields
  (full amended claim text). Longest record mechanically wins. Normalize by length or
  weight by IDF.
- [ ] **C3 · Give the store a write API.** `LoopholeStore` has no `add()` and no `save()` —
  it is read-only by construction, which is precisely why D exists as a separate block.
- [ ] **C4 · Decide the knowledge graph question, and say so.** There is **no graph in
  code** — no `networkx`, no node/edge types, no traversal. The "graph" is one boolean
  equality on `technology_class`. `README.md:8` and `docs/ARCHITECTURE.md:80,105-110`
  assert a persistent knowledge graph as fact. Either build edges (statute ↔ claim shape ↔
  CPC class) or change the prose. Do not walk a judge into that gap.
  Note `db/schema.sql` already designed the richer shape — `statutory_defect_category`,
  `cpc_class`, confidence and provenance columns — before it was abandoned for flat JSON.
  It is dead (`duckdb` is still an unused dependency), but it is a good spec for C1.

### D · Ingest → memory — close the circuit

**The circuit is open.** `agent/ingest.py` imports only `airtight.config` and
`airtight.guardrails` — never `agent.memory`, never `LoopholeRecord`. `ingest_document`
(`:44-49`) returns the admitted text, and every caller drops it: `:87` uses it for `len()`
in a print at `:103`; `agent/poison_demo.py:71` checks it for `None`. The
`"loophole report: attempted indirect injection recorded"` line at `:98-99` is a **print,
not a write** — nothing is recorded anywhere, and `g.QUARANTINE_LOG` / `g.AUDIT_LOG`
(`airtight/guardrails.py:90-91`) are module-level lists that die with the process.

Ingest is a security demo with a CLI. It is not a data path.

- [ ] **D1 · Distill admitted text into records.** Don't write a new prompt —
  `DISTILL_SYSTEM` (`data/distill_loopholes.py:28-35`) already emits exactly
  `{pattern, claim_shape, remedy}` and `_parse_json` (`:38-46`) already handles extraction.
  Wrap it as `distill_text(text, source, tech_class) -> list[LoopholeRecord]`, routed
  through `call_model` so the doorway and guardrail hop still fire.
- [ ] **D2 · Write, then merge into retrieval.** Persist to `memory/ingested/` and merge
  via `CompositeStore` (`agent/episodes.py:112`), which already does base+extra merging
  with id-dedup. `LoopholeStore.load` accepts both list- and object-shaped files, so a flat
  directory needs no loader change. Depends on C3.
- [ ] **D3 · Quarantined content must never reach memory — and this is the story.**
  Ingest is the poisoned-PDF path (`data/fixtures/poisoned_prior_art.pdf`, two hidden
  vectors, live-verified against real HiddenLayer). Wiring ingest into memory without a
  gate would let an attacker write directly into the agent's long-term store — a
  persistent, compounding injection. The HiddenLayer bus is what makes D safe, and
  `INGESTED_DOCUMENT` already fails **closed** (`airtight/guardrails.py:84`).
  **Say this on stage:** Track 2 isn't a bolt-on next to Track 1 — it's the precondition
  for it. A learning agent that ingests untrusted documents *must* have a scanner on that
  hop, or its memory is an attack surface. Add the test that proves a quarantined document
  leaves zero records behind.

**Done when:** a document read at ingest changes what the agent retrieves on the next run,
and a poisoned one provably does not.

---

## Done

- **Data (E1–E5)** — 134 patents across G06N/G06F/H04L with real abstracts and claims;
  94 held-out checklists; 193 defects mined from real office actions (§103 ×111, §101 ×27,
  §112 ×39, §102 ×16). Tracked in git — `main` gets you the data, no key needed to consume.
  Overlap guard green: 0 id collisions, 0 Jaccard flags. Two-vector poison PDF real and
  extractable through `agent/ingest.py:_extract_text`. Dead `src/` pipeline and both
  data-fabricating scripts quarantined under `attic/`.
- **Inference (F1–F4)** — Nemotron 3 Nano on vLLM → Modal free tier; `inference.local`
  live; one-var `INFERENCE_BACKEND=modal|nim` flip with all three backends verified green;
  `runtime/RUNBOOK.md` handoff. Judged GPU profile is **`a100-bf16`**, chosen on recovery
  time not price: `l40s-fp8` is faster *and* cheaper (865 vs 696 tok/s, $1.95 vs $2.50/hr)
  but cold-starts in **~12 min** vs ~1–2, and Modal preempts containers. The "~2–5 min cold
  start" in the old docs was wrong on both profiles. Weights pinned to a per-profile commit SHA.
- **Doorway (G0)** — single legal model hop (`airtight/doorway.py:58`), `AIRTIGHT_MODE`
  defaults to `stub` so a fresh clone runs offline, and the no-other-client rule is
  *enforced* by `tests/test_smoke.py:22`, not just documented.
- **Guardrails (M2)** — all five hops and all four graded actions implemented, fail-closed
  on `TOOL_CALL` and `INGESTED_DOCUMENT`. **Live-verified 2026-07-18** against the real
  AIDR API: the poisoned doc flagged as `prompt_injection`, real `event_id`. **All five
  hops now fire in one real flow** — `agent/poison_demo.py` wraps `prior_art_search` in
  `@g.guarded_tool` (`:26`) for the two tool hops and ingests the poisoned document,
  alongside the doorway's user_prompt/model_response. One caveat left: this key's ruleset
  flags injection but not PII, so the graded *redact* path is a tested capability, not a
  live demo beat.
- **Eval harness (M4)** — paired runs, `scaffold_proof()` asserting byte-identical
  templates outside the memory slot, a hard leakage guard, a config fingerprint with git
  SHA + prompt hashes, and a blinded judge that downgrades any verdict whose quoted
  evidence isn't literally in the claims. Stub mode has zero delta by construction, so a
  green suite proves plumbing, not effect. Doorway timeout and `--deadline-min` landed
  after the `--n 10` run hung on a call with no timeout and burned GPU credit.
- **Surface (D1, D2, D4)** — idea → draft → patent, wired to the real agent loop, not
  mocked. One static HTML file, no build step.

---

## Open risks

| Risk | Plan |
|---|---|
| **Both live numbers were produced by retrieval that no longer exists** | C1 landed, so the 5/6 and the backwards 4/10→1/10 are both pre-fix measurements. **This is now the top open item on the board:** one GPU window, pooled over `data/real/`, plus a re-run of the distilled-FWD set. Until it lands, no delta is quotable — including the good one |
| **The ablation headline also rests on a deleted input** | The 5/6 ran on `data/real-eval/`, absent from the tree. Re-derive from the tracked corpus in the same re-run rather than trying to reconstruct it |
| NemoClaw preview won't stand up (A1) | It's a small binary go/no-go — attempt it **early**, fail fast, fall back to §8 on a remote Linux host in the same four-tier vocabulary |
| Judges find an egress path the policy never covered | That is exactly what A5 is for. Don't skip it to save time |
| Docs claim enforcement the code doesn't have | `docs/ARCHITECTURE.md:95,236` assert real Landlock enforcement and real Policy-Advisor HITL. Both collapse under a `grep openshell`. Fix the prose or build the thing — C4 is the same problem for the knowledge graph |
| **Two implementations of the one hop** | `airtight/doorway.py` and `runtime/inference_local.py` are parallel clients for the same operator-pinned boundary. Not broken, but "one boundary, three tracks" currently has two doorways. Steven + Anudeep pick the canonical one and delegate the other — see `docs/INTEGRATION-STATUS.md` |
| Compounding poisons its own corpus | B3 before B2. Non-negotiable ordering |
| Modal cold start / credits | Keep the app **paused** by default; `min_containers=1` only in the demo window; NIM is one env flip away |

---

## Standing rules

- **The Modal app stays paused.** Un-pause only for a step that genuinely needs the GPU,
  re-pause immediately. Pausing is the operator's call — ask, don't do it unprompted.
- **Build against `runtime/mock_endpoint.py` first.** Debugging on a metered cold start is
  how the credit disappears. Get it green offline, then spend one short scripted live window.
- **Check for concurrent sessions before a metered run** — another agent can wake or
  redeploy the app mid-measurement.
- **Finish a task by updating this file in the same change.** Record partial and failed
  outcomes with the same care as wins; the entries that have saved the most time here are
  the honest ones.
