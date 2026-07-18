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
| **Inference** | ✅ first half | Nemotron on vLLM/Modal, `INFERENCE_BACKEND=modal\|nim\|gateway`, 10.67× batching on record; `inference.local` gateway injects creds host-side (A4) |
| **Agent** | ◐ built, shallow | loop + guardrails + eval harness all real and tested; memory is static RAG, nothing compounds |
| **Containment** | ✅ real enforcement (Plan B) + LIVE | offline demo (A3/A6); **`containment/planb/` enforces the four tiers on a Linux kernel — real 403, non-root, read-only fs, no route off-box (A1 Plan B, A5 sweep)**; **LIVE online at https://airtight-openshell.vercel.app — real `policy.decide`, real HTTP 403 over the internet, operator approve/reject (`containment/live/`)**. Vendor `nemoclaw` binary still DGX-gated; judged run deploys the same compose to a remote host |
| **Surface** | ◐ starter | idea → draft → patent works; edit boxes discard input; no chart view |

Suite: `.venv/bin/pytest tests/` → **84 passed**, 0 skipped, stub mode, no network.
(The gateway's full 3-process end-to-end proof is `python -m runtime.gateway_smoke`, kept
out of the suite so `pytest tests/` stays server-free.)

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

Four blocks, in dependency order. **A3, A4 and A6 landed 2026-07-18** (escalation client
wired into the demo, OpenShell↔HiddenLayer fusion live, `inference.local` gateway injects
creds host-side — all verifiable offline). **A1 (Plan B) and A5's sweep are now real too**
— `containment/planb/` enforces the four tiers on a Linux kernel with a real 403, verified
end-to-end; what remains is the **remote-host deploy** for the judged run and the gated
NVIDIA binary. **B, C and D are unblocked and can start today.**

### A · Containment — make OpenShell real

Today: `containment/policy.py` is a genuine, data-driven, tested policy evaluator, and
everything around it is theatre. `containment/openshell_sim.py:5-6` says so in its own
docstring. Every "403" is a `print()` (`:29`, `:36`). `attempt_egress()` never opens a
socket. No `openshell` or `nemoclaw` binary is installed anywhere — every occurrence in
the repo is prose or an f-string.

- ◐ **A1 · Stand up the sandbox — Plan B BUILT & verified 2026-07-18; vendor binary still
  DGX-gated.** Two paths:
  - **Primary (NVIDIA `nemoclaw`/OpenShell):** still a go/no-go on **hosted DGX Spark** —
    gated preview, can't be reached from here. Steps (CLI verbs UNVERIFIED): `ONBOARDING.md`.
  - **Plan B (`research/…` §8) — now REAL, not just described:** `containment/planb/` stands
    up the four-tier model on a stock Linux kernel and is **verified end-to-end**
    (`bash containment/planb/run.sh`): a docker `internal` network gives the sandbox **no
    route off-box** except the egress gate (network tier); the sandbox runs **non-root,
    cap-drop ALL, no-new-privileges, read-only fs** (process + filesystem tiers, empirically
    checked — `CapEff: 0` and a write to `/app` fails); the gate runs the **real**
    `containment.policy.decide()` and returns a **real socket-level 403** (policy tier). The
    trick prompt is blocked by real 403s with the real approve/reject escalation.
  **What's left:** deploy the *same* compose to a **remote** Linux host for the judged run
  (never local/venue), and — if the preview stands up — swap the container gate for the vendor
  binary. The graded architecture and the real 403 are done; the venue deployment is a `docker
  compose up` on a remote box.
  **One honest caveat (`containment/planb/README.md`):** the gate's *path*-level discrimination
  (same host, `allow /search/**` vs `hard-deny POST /filings/submit`) works because the demo
  uses plain-HTTP forward-proxy requests; production HTTPS `CONNECT` shows the gate only
  `host:443`, so path-granularity needs TLS termination at the gate (what OpenShell does). The
  network/process/filesystem isolation and host-level allow/deny are protocol-independent and fully real.
- ◐ **A2 · Make the policy YAML enforce — done 2026-07-18 except the live-schema check (DGX).**
  1. **`enforce` on the inference endpoint — DONE & verified.** The original complaint was
     that "strictness only exists as a Python default arg" — no longer true: `containment/
     policy.py` now **reads the per-endpoint `enforcement:` field**, so the artifact drives.
     `inference_gateway` and the sensitive `filing_api` ship `enforce`; read-only discovery
     endpoints (`patent_sources`, `client_datastore`) stay `audit` for the A5 full-agent
     sweep. Proven by `test_enforcement_field_drives_the_decision` (flip the field → the
     decision flips) and enforced for real in Plan B (`ENFORCE=enforce` → real 403).
  2. **Two inference destinations — DONE.** Both are now enumerated in `inference_gateway`
     (owner decision, 2026-07-18): `inference.local` (the A4 gateway), the Modal serve host
     (PRIMARY, `$500` bounty path) and `integrate.api.nvidia.com` (NIM FALLBACK) — **all
     `enforce`**. The operator pins one backend (`INFERENCE_BACKEND=modal|nim`); the A4 gateway
     also resolves both (tested: `test_gateway_resolves_operator_upstream_from_the_one_table`
     + `test_gateway_resolves_the_nim_upstream_too`). Tradeoff recorded in the YAML comment:
     listing the two backends directly also permits the pre-gateway path; the gateway is what
     keeps creds host-side once deployed.
  3. **Validation — LOCAL structural check DONE; live schema still DGX.**
     `inference/policy/validate_policy.py` (`python -m inference.policy.validate_policy` + 3
     tests) checks the four tiers, enforcement modes, rule shapes, and the inference hop. The
     live early-preview schema check remains on the box (`ONBOARDING.md` "Things to confirm").
- [x] **A3 · Wire the Policy Advisor client in — done 2026-07-18.** `containment/demo.py`
  now calls `PolicyAdvisorClient.escalate()` (`agent/policy_advisor.py`, landed `0878a5f`)
  on every default-deny; the hardcoded `proposal_flow()` prints are gone and
  `openshell_sim.proposal()` renders the **real** `Proposal` object the client returned.
  Both branches run in the demo: Dropbox → `MockTransport(approve=False)` → rejected with a
  real `chunk_id`/reason; a legitimate un-allowlisted prior-art host →
  `MockTransport(approve=True)` → approved → the retry proceeds. The filing hard-deny is
  **not** escalated (tested: `transport.submitted == []`). `grep -rn PolicyAdvisorClient`
  now returns the demo, not just its own test. Four new tests in `tests/test_containment.py`.
  **Scope, honestly:** the deny and the approvable/rejectable proposal are now real
  (decision from the YAML, proposal from the injectable client) — but the "403" is still a
  `[SIM]` line, not a socket-level refusal from an enforcing gateway. That last mile is
  A1/A4, not A3.
- [x] **A4 · Close the two honest gaps — code side done 2026-07-18, verified offline.**
  `runtime/inference_gateway.py` is a real, stdlib-only OpenAI-compatible gateway process
  in front of `inference.local`. New backend `INFERENCE_BACKEND=gateway`
  (`runtime/inference_local.py`) points the agent at it with a **dummy** token; the gateway
  strips it and injects the operator's real key **host-side** before forwarding upstream,
  and pins the model (the agent can override neither endpoint nor model). It reuses the one
  `_resolve()` backend table — no third divergent copy. **Proven end-to-end with no GPU**
  (`python -m runtime.gateway_smoke`, 3 real processes): the sandbox's dummy token is
  rejected talking to the provider directly (401) yet works through the gateway (200), the
  model is pinned, and the provider key is absent from the agent's env. Four hermetic unit
  tests in `tests/test_gateway.py`.
  **Scope, honestly:** this is the credential-injection + name-resolution half. Two things
  remain — (a) mapping the literal name is a one-line operator step
  (`127.0.0.1 inference.local` in `/etc/hosts`; can't `sudo` from here); (b) the *guarantee*
  that a sandboxed process can't reach the host's env by some other path is OpenShell's
  Landlock/seccomp isolation — **A1**, Linux-only. So: the agent now holds no provider
  credential and the gateway is a real hop; the isolation that enforces it is still A1.
- ◐ **A5 · Audit → enforce sweep — demonstrated for real in Plan B 2026-07-18.** The gate
  honours `ENFORCE=audit|enforce`: `ENFORCE=audit bash containment/planb/run.sh` **logs the
  real egress set and lets it through** (observe — `[gate:audit] hard_deny POST
  api.uspto.gov/filings/submit`, …), then default `enforce` turns each into a real 403. That
  is the literal audit→enforce sweep, on real sockets. **What's left:** run the *full patent
  agent* inside the sandbox (today the driver is the adversarial trick-prompt probe, not the
  whole loop — that needs the runnable agent, so still after B) and do the sweep on the real
  egress set the full agent produces, which is where an un-covered egress path (the named top
  risk) would surface.
- [x] **A6 · Fix the dead M2 fusion — done 2026-07-18.** The demo now has a beat where
  policy **ALLOWs** and HiddenLayer **still acts**, on one action: the vault read is allowed
  by `policy.decide`, and the returned disclosure bytes are quarantined by the guarded_tool
  `TOOL_RESULT` hop (observable in the run — the bytes come back as the quarantine
  placeholder, not the disclosure). That is the "one boundary" story made real: two
  independent gates on the same action, not a `guarded_tool` block stranded behind a deny.
  The bus is the same code path live-verified in `agent/poison_demo.py`, but the *detection*
  in this beat is scripted deterministically (a PII flag — which this key does not raise
  live; see the M2 caveat under Done), exactly as the tests monkeypatch it and as
  `MockTransport` scripts the operator, so the fusion is observable offline. `containment/fixtures/exfil_request.json` is
  now the demo's source of truth (prompt, forbidden/approvable/allowed actions), so it is
  read, not dead. Test: `test_allow_action_still_crosses_hiddenlayer_and_quarantines`.

**Done when:** the trick prompt *"file now + back up to Dropbox"* is blocked by policy the
operator set — filing by `deny_rules`, Dropbox by un-allowlisted egress — with a real 403,
and a proposal the operator can actually approve *or* reject.

**Status (2026-07-18):** three of the four clauses are real — the block is decided by the
operator's YAML (`policy.decide`), and the proposal is a real approvable-*or*-rejectable
object from `PolicyAdvisorClient` (A3), both demonstrable via `python -m containment.demo`.
The one clause still open is *"a real 403"*: today it is a `[SIM]` line, because a
socket-level refusal needs an enforcing OpenShell gateway (A1) and host-side creds (A4),
which need Linux/DGX hardware. So: **deny + proposal are real; the literal 403 is not yet.**

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
- [x] **C2 · Normalize the overlap score — done 2026-07-18.** `agent/memory.py::_rank` now
  **IDF-weights the overlap** instead of a raw token count: common tokens (claim, method,
  device, system) count for almost nothing, rare distinctive ones carry the match, so a
  short record sharing the disclosure's specific vocabulary outranks a long one that merely
  overlaps on boilerplate. Deterministic. Tested (`test_c2_idf_overlap_beats_raw_length`).
- [x] **C3 · Give the store a write API — done 2026-07-18.** `LoopholeStore` now has
  `add()` (dedup by id), `add_all()`, and `save()` (flat `<id>.json`, the layout `load()`
  reads). This is what block D writes through. Tested (`test_c3_write_api_add_dedups_and_saves`).
- [x] **C4 · Decided (and said so) — 2026-07-18: no graph; it's retrieval over a flat store.**
  There is no `networkx`, no node/edge types, no traversal, and building one is not worth it —
  the mechanism that actually moves the ablation is **statute-diversified, IDF-ranked
  retrieval over an episodic record set** (C1 + C2 + block B), not graph traversal. The prose
  is corrected to match: `README.md` no longer asserts a "persistent knowledge graph" (now
  "persistent, statute-indexed failure library … a flat record set, not a graph");
  `docs/ARCHITECTURE.md:7` already flags the graph sections as design-not-code. `db/schema.sql`
  and the unused `duckdb` dep remain the abandoned richer shape — a future upgrade, not a claim.

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
| Docs claim enforcement the code doesn't have | **Materially reduced 2026-07-18:** `containment/planb/` now *is* real enforcement (real 403, non-root, read-only fs, no route off-box — verified). Real Policy-Advisor HITL is wired (A3). Still audit the prose in `docs/ARCHITECTURE.md:95,236` to say "Plan B container isolation, verified locally; vendor OpenShell binary DGX-gated" rather than implying the NVIDIA product runs today. C4 is the same problem for the knowledge graph |
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
