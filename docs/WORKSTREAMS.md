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
| **Agent** | ◐ built, deepening | loop now self-corrects (revise turn) and compounds (episodic write, isolated from the ablation); retrieval is statute-diversified and BM25-ranked, and ingest writes into it. B, C and D all done offline — **every quality gain is still unmeasured live** |
| **Containment** | ⚠️ simulated | `policy.py` decision logic is real, and now so is an escalation client — but enforcement is still a `print()`. No OpenShell exists |
| **Surface** | ✅ two frames | intake (retrieval → live pipeline → grant) + engine panel over every committed artifact; D3's dishonest edit boxes replaced with a labelled seam |

Suite: `.venv/bin/pytest tests/` → **156 passed**, 0 skipped, stub mode, no network.

📌 **Unrecorded on this board:** `main` gained live USPTO prior-art search
(`agent/prior_art.py`) and an MPEP statute reference grounding the draft/critique/revise
loop (`agent/statute_reference.py`) at `5e5f9eb`/`f85faa7`, +11 tests, with no lane entry.
Both claim product-path-only isolation from the M4 ablation. Noted here so it isn't lost —
**not verified by the Surface lane**; the author should grade it against the notation above.

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

Four blocks, in dependency order. **B, C and D are done (2026-07-18)** — B landed in a
separate tree and merged at `d899e26`, which surfaced the collision closed by `201e8f8`.
A3 remains unblocked and can start today; only A1/A2/A4/A5 wait on hosted hardware.

**The single highest-leverage item is still the GPU re-run** — C1 and now C2 both changed
retrieval, so neither live ablation number is quotable until it lands. Retrieval is sound
and offline-validated; the measurement is the last step.

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

**Done 2026-07-18 (`e4f6fcd`), B3→B1→B2 order. Loop now self-corrects and compounds; the
one thing left is measuring the live quality gain (needs a GPU window — the mechanism is
proven offline).**

- [x] **B1 · Revise turn — done.** `draft_patent` (`agent/loop.py`) gains `max_revise_rounds`
  (default 1): plan → draft → critique → **while `material_defects(critique)`: revise → re-critique**.
  `claims`/`specification` are now POST-revision (the pre-critique-text bug is fixed);
  `critique_notes` keeps the INITIAL critique (the mistakes the episode learns from). Stub
  replies carry no defect keyword, so stub does 0 revises and the ablation stub-delta-0
  invariant is untouched. `REVISE_SYSTEM` is in `scaffold_proof` + the fingerprint;
  `revise_rounds` is stamped; `--revise-rounds` on the CLI. Tests: `tests/test_revise.py`.
- [x] **B2 · Episodic write — done.** The dead `EPISODES_ENABLED` now gates the write
  (`sink AND flag`). **Isolation is absolute:** the harness passes no sink, so no env flip
  writes during the ablation — regression-locked by `test_ablation_uncontaminated_by_episodes`
  (now with the flag *on*). Verified: `run_smoke --episodes` run 1 wrote an episode, run 2
  retrieved it ("0 past" → "1 past"). Real quality gain still needs a live multi-run; the
  compounding *mechanism* is proven offline.
- [x] **B3 · Bounded distillation — done (first, as required).** New deterministic
  `material_defects()` keeps only critique lines naming a §NNN or defect keyword; `compress_run`
  distills a CAPPED (`DISTILL_CAP=3`), cleaned set with `§NNN` in the pattern so the validator
  derives `.statute`. Headers/preambles/bare bullets never become records. Tests cover the
  filter, the cap, and no-poison-in-stub.

Correctness items closed: the `rglob` (episodes, subdirs) vs `glob` (flat corpus) difference
is now documented as intentional on both; `.gitignore` is `memory/episodes/**/*.json`, so
subdir episodes are actually ignored. **Re-verified after the C/D merge 2026-07-18** —
`git check-ignore` matches a freshly written `memory/episodes/<id>/x.json`, so this is
observed, not reported. The C/D rule `memory/ingested/*.json` stays a one-level glob on
purpose: `LoopholeStore.save` writes flat, so `**` would claim a nesting that never occurs.

### C · Context memory — make retrieval right ✅ done 2026-07-18

`agent/memory.py` ranks on a 3-tuple: `technology_class` exact match, **BM25 relevance**,
then `rec.id` reverse-alphabetical. The store is still a plain Python list hydrated from a
flat JSON directory — no index, no embeddings — but it now retains its directory and can
be written to. All four items closed; read C2's caveat before quoting it.

⚠️ **Two cross-lane contract additions landed with this block** (`airtight/` is the frozen
shared contract, so they are called out here rather than buried):
`LoopholeRecord.extraction_confidence: float = 1.0` (`airtight/shapes.py`) — semantics and
default lifted from `db/schema.sql`'s column of the same name, optional so all 193 tracked
records validate unchanged, and **unread by `loop.render_guardrails`, so it cannot perturb
the ablation prompt** (asserted by `test_extraction_confidence_cannot_perturb_the_prompt`).
And a `"distill"` role on `doorway.Role` + `airtight/stubs.py` — without a record-shaped
stub reply, the ingest write path yields zero records offline and would look wired while
doing nothing on a fresh clone.

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
- [x] **C2 · Rank by BM25 — done 2026-07-18, offline-validated. Read the caveat.**
  `_rank` (`agent/memory.py`) now scores IDF-weighted matches with BM25 length damping
  instead of a raw overlap count. Measured on the real pooled split (10 graded
  disclosures, 167-record corpus, no GPU):

  | | raw (before) | **BM25 b=0.3 (shipped)** | `overlap/len` |
  |---|---|---|---|
  | cross-disclosure top-5 Jaccard | 0.172 | **0.098** | 0.205 |
  | distinct records used across 10 | 23 | **29** | 26 |
  | checklist statutes covered | 10/10 | **10/10** | 10/10 |
  | retrieved-set length percentile | 0.815 | 0.792 | 0.521 |
  | bloat promoted over both parents | 100% | 97% | 8% |

  **What actually improved is disclosure-specificity, not length bias.** Cross-disclosure
  Jaccard falling 0.172 → 0.098 means retrieval stopped handing the same big records to
  every disclosure — that is the property the ablation rewards, and it comes from **IDF**,
  which is already fully present at `b=0`. Length percentile barely moved (0.815 → 0.792)
  and the bloat probe barely moved (100% → 97%): **C2 as shipped does not fix "longest
  record wins" in the direct sense this item originally proposed**, and the board should
  not claim it does.
  That was deliberate. `b` (length-normalization strength) trades directly against
  resistance to episodic noise, measured over the same 10 disclosures — how often a
  `compress_run`-shaped record built from the disclosure's own vocabulary lands in the top 10:
  `b=0.3` → **1/10** · `b=0.6` → 7/10 · `b=0.75` (textbook default) → 7/10 · `b=1.0` → 9/10 ·
  `overlap/len` → **10/10, and rank #1 for every one of them**. Raw scored 0/10.
  So the literal instruction in this item — "normalize by length" — would have handed B2/B3
  a corpus where self-generated noise outranks every real PTAB record by construction.
  `b=0.3` keeps the retrieval win and the noise resistance; it gives up the bloat fix,
  which is the weakest of the three signals (a record holding two real patterns genuinely
  *is* relevant to queries matching either). The sweep table is in the code at the constant.
  Determinism: IDF is summed over a `sorted()` intersection (set-of-strings iteration order
  varies with `PYTHONHASHSEED` — verified, and a subprocess test pins it) and the score is
  `round(…, 6)` before it enters the sort key, so a libm difference can't reorder near-ties.
  All 70 pre-existing tests pass unmodified; 6 new ones in `tests/test_retrieval_ranking.py`.
- [x] **C3 · Give the store a write API — done 2026-07-18.** `LoopholeStore` now retains
  the directory it loaded from and has `add()` (in-memory, id-deduped, **zero I/O**) and
  `save()` (one flat `<id>.json`). `merged_store(*stores)` returns a plain `LoopholeStore`,
  so it still satisfies `CompositeStore`'s `base` contract — that is what let D compose
  ingested memory with episodes **without editing `agent/episodes.py`**.
  `empty()` keeps `directory is None`, so the ablation's control arm is structurally
  incapable of persisting anything. `self.records` is still a plain list, because
  `CompositeStore` and `assert_no_overlap` both reach for it directly.
  12 tests in `tests/test_memory_write.py`.
- [x] **C4 · Knowledge graph — decided: the prose was wrong, so the prose changed.**
  There is no graph in code and none was built. Building one would have been a second
  ranking change inside the window before the GPU re-run — the exact mistake this board
  already records once — and the honest description costs nothing: after C1+C2 the system
  has statute-diversified, IDF-ranked, CPC-gated retrieval over a persistent failure
  library, which is a real mechanism that just isn't a graph.
  Fixed: `README.md:8` ("persistent knowledge graph" → "persistent failure library —
  records indexed by statutory basis, CPC class and claim shape"), `README.md:12`,
  `README.md:22`, and `docs/JUDGING-RUBRIC.md:38`.
  **`docs/ARCHITECTURE.md` deliberately left alone** — `:7` already carries a "design spec,
  not a status report" disclaimer naming this exact gap. README and JUDGING-RUBRIC carried
  no such hedge, which is why they were the exposed ones.
  If the graph is ever built, `db/schema.sql` remains the good spec (`statutory_defect_category`,
  `cpc_class`, confidence and provenance columns), and it should be retrieval-neutral so it
  can land without invalidating a measurement.

### D · Ingest → memory — close the circuit ✅ done 2026-07-18

**The circuit is closed.** It was open: `agent/ingest.py` imported only `airtight.config`
and `airtight.guardrails`, `ingest_document` returned admitted text and every caller
dropped it, and the `"loophole report … recorded"` line was a print, not a write. Ingest
was a security demo with a CLI, not a data path.

It is now a data path with a gate on it: `ingest_to_memory()` distils admitted text into
the store via `agent/distill.py`, and quarantined text stops one line earlier — upstream
of the model, not merely upstream of the disk.

- [x] **D1 · Distill admitted text into records — done 2026-07-18.** New `agent/distill.py`
  holds the extraction contract both producers share. It lives in `agent/` rather than
  `data/` because `data` is not a packaged module — `agent.ingest` importing `data.…` works
  from a checkout and breaks in a wheel; `data/distill_loopholes.py` now imports *up*.
  `DISTILL_SYSTEM` moved byte-identically (sha256 pinned in a test, verified against git HEAD).
  **`INGEST_SYSTEM` is deliberately a different prompt**: `DISTILL_SYSTEM` asserts "a PTAB
  Final Written Decision held patent claims unpatentable", which is false about an arbitrary
  ingested document — feeding the model a false premise to get a plausible record is how
  fabricated memory gets minted. Only the JSON contract is shared.
  `distill_text(text, source, tech_class)` yields **at most one record, by function arity**
  — not a cap applied afterwards. That is the structural fix for the shape B3 flags in
  `compress_run` (one record per *line* of a reply). Ids are `sha256` of the **input**
  (`ing-<12 hex>`), never the reply, so a nondeterministic live model cannot mint a second
  id for the same document and re-ingest is idempotent. Input truncated to 6000 chars.
  `tech_class` **raises on a `TC####` value** — `distill_loopholes._tech_class` emits USPTO
  Technology Centers, which can never equal a `Disclosure`'s CPC class, so such a record
  would be permanently invisible to retrieval. Filenames are stripped of `§()` before
  entering `source`, or an attacker-named file could pick its own statute bucket.
  9 tests in `tests/test_distill.py`.
- [x] **D2 · Write, then merge into retrieval — done 2026-07-18.** Records persist flat to
  `memory/ingested/<id>.json` (`config.INGESTED_DIR`, gitignored with a tracked `.gitkeep`).
  Retrieval merges them behind a new `--ingested` flag on `agent/run_smoke.py`, layered so
  the two sources stay orthogonal — **the `--episodes` B2 gate is untouched and its
  retrieval path is verified identical to the pre-change wiring.** `CompositeStore` needed
  no edit: `merged_store` composes one layer below it.
- [x] **D3 · Quarantined content never reaches memory — done 2026-07-18, and this is the
  story.** The gate is `ingest_document`'s existing `None` return, and it is the only one,
  so `distill_text` is unreachable past a quarantine. **The stronger claim, and the one to
  say on stage: a poisoned document never reaches the model at all** — the gate sits
  upstream of `call_model`, so no tokens are spent on attacker content and the doorway
  never sees it. `GuardrailBlocked` propagates uncaught by design (catching it inside
  `ingest_to_memory` is precisely the bug that would reopen the hole).
  The test asserts the model was never *called*, not merely that no file appeared —
  verified to fail when the gate is removed. Also hardened `ingest_document` to return
  `verdict.text` rather than the raw input: a no-op today, but the moment anyone maps
  `pii → REDACT` onto this hop, the old code would have persisted un-redacted text.
  The `:98-99` line this board called out as "a print, not a write" is now true — it cites
  the `results/security/quarantine.jsonl` record and the event id.
  10 tests in `tests/test_ingest_memory.py`, plus `test_ablation_uncontaminated_by_ingested`
  in `tests/test_eval.py`.

**Post-review hardening (2026-07-18).** A multi-agent review of the C/D diff confirmed 10
defects; all are fixed, and the ones worth knowing about were places where the code did not
do what its own docstring claimed:

- **`ingest_to_memory` had no gate at all with the bus OFF — which is the default.**
  `HL_ENABLED` defaults false, `g.analyze` then short-circuits to PASS, so the quarantine
  check could never fire and an unscanned document was distilled and persisted. Verified by
  the reviewer, and *no test covered it* because every test called `hl_on()` first. Now
  raises `UnscannedIngest`, and the CLI refuses `--remember` with exit 2 instead of
  reporting success while writing nothing.
- **Provenance was written only into `source`, which `render_guardrails` drops** — so an
  inferred record reached the drafting prompt formatted exactly like a PTAB-mined one. The
  marker now rides in `pattern`, which *is* rendered. Kept out of `agent/loop.py`, so the
  ablation scaffold hash is untouched.
- **`--memory-dir` accepted any path**, so `--memory-dir data/corpus/loopholes` would write
  a confidence-0.3 record into the git-tracked graded corpus. `save()` now refuses anything
  under `data/`.
- **`_rank` keyed its token cache by `rec.id`** — last-wins, so duplicate ids (which
  `load()` does not dedup) scored every copy with the last one's text. A regression C2
  introduced; the overlap count it replaced tokenized inline and was immune. Now keyed by
  position.
- **`_safe_source` stripped `§()` but `_STATUTE_RE` also matches `\s`**, so
  `Office Action 101.pdf` still injected a statute — and the test covering it **passed for
  the wrong reason** (the stub pattern already contained `§112`, so `statute_of` returned
  before reaching `source`). Both fixed; the test now asserts against `statute_of` directly.
- `save()` no longer overwrites a record `add()` refused (disk and memory could disagree
  after a reload).

Two of the new regression tests were themselves verified to *fail* against the reintroduced
bug, because the first version of the duplicate-id test passed under sabotage.

**Done when:** a document read at ingest changes what the agent retrieves on the next run,
and a poisoned one provably does not. ✅ **Both halves observed end-to-end, stub mode, no
network** — `python -m agent.run_smoke --ingested` retrieves 5 corpus records; after
`python -m agent.ingest data/fixtures/prior_art_clean.txt --fake-clean --remember
--tech-class G06F`, the same command returns `ing-644d1b8495b7` (§112, confidence 0.3) in
the retrieved set, displacing `lh-w-006`; after ingesting the poisoned PDF with
`--fake-detect --remember`, the retrieved set is byte-identical to the run before it and
`memory/ingested/` still holds exactly one file. Full sequence in `README.md`.

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
- **Surface (D1–D5)** — two frames, static HTML/CSS/JS, no build step, one `uvicorn`.
  *Intake* (`/`): disclosure → retrieved context → live pipeline → grant. Retrieval runs
  as you type (BM25 only, no model call), and drafting goes through a job + poll so the
  loop's turns are visible instead of a multi-minute spinner — polling, not streaming,
  which sidesteps the upstream `reasoning_content` bug. *Engine* (`/admin`, the old D5):
  corpus facets, a retrieval inspector that shows which higher-ranked records
  diversification passed over, the ablation, the guardrail bus, the throughput curve, and
  the four containment tiers. Read-side logic is in `surface/sources.py` +
  `surface/explain.py`; neither touches `agent/memory.py` or `agent/loop.py`.
  - **Two engine bugs fixed on the way.** `POST /api/draft` never passed `guardrails`, so
    every UI draft silently ran the ablation's *control* arm and reported it as the
    product — `loopholes_closed` was structurally always `[]`. And `g.AUDIT_LOG` was read
    whole after each draft, so every request re-reported every earlier request's findings.
    Both now have regression tests that were confirmed to fail against the old code.
  - **`◐` D3 is still `◐`, deliberately.** Claims render read-only behind an
    `EDITING NOT WIRED` seam naming `PATCH /api/draft/{job_id}`. The textareas that
    silently ate every edit are gone; real editing is still unbuilt.
  - **Ten defects found by review and fixed, with regression tests.** The offset fix
    above was only correct for *sequential* requests — two overlapping drafts interleave
    in `AUDIT_LOG` and cross-attribute, which is worse than the original bug because it is
    wrong *and* plausible. Drafts are now serialized process-wide (`jobs.exclusive_draft`);
    per-job attribution would have to come from the guardrails bus, which this lane does
    not touch. Confirmed failing with the lock removed. The rest were the read layer
    breaking its own "nothing raises" contract on plausible on-disk shapes — malformed
    YAML (`yaml.YAMLError` is not a `ValueError`), null-valued keys (`.get(k, {})` returns
    `None`, not `{}`), a `results.json` holding a bare list, a null `ts` breaking
    `sorted()`, a one-level sweep dividing by zero in the chart. Worst of them:
    `_load_store` wrapped the whole directory load, so **one truncated record emptied the
    corpus** — and an empty corpus does not fail loudly, it silently drafts every patent
    in the control arm. Loading is now per-file with a skipped-record seam.
  - **Two panels were stating things that were not true** and now compute them: the
    retrieval inspector asserted the passed-over rows had out-scored a pick (only true
    when diversification actually cost something), and the score column could contradict
    its own rank column because `_rank` sorts on class-match *before* BM25.
  - **Found, not fixed:** `guardrails._persist()` writes unconditionally, so `pytest`
    appends to the same `results/security/*.jsonl` the demo reads. All 130 audited hops in
    the current log are fixtures (`e`, `evt-test`, `fake-*`) — **zero** carry a real AIDR
    UUID, including the live run documented on 2026-07-18. The bus panel splits live from
    synthetic and says so rather than showing 77 test-suite blocks as agent activity.
    `tests/test_surface.py` redirects `_SECURITY_DIR` to `tmp_path`; the other suites
    that write there do not.

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
| **`diversify_by_statute` sold a guaranteed top-k slot to any sparse statute bucket — half fixed 2026-07-18, half still open for B** | **D-side closed; B-side still open by scope decision.** The round-robin takes one record from *every* bucket before any bucket yields a second, so a record's slot depended on how rare its statute is, not on its score. Found by code review to be broader than the original B-lane note, and to bite D directly: the ingested `ing-644d1b8495b7` took **position 2 of 5** in the README demo, and on the real corpus a record with *zero* token overlap and the wrong CPC class still took slot 5, evicting a real PTAB record. **Fixed for untrusted records:** only records at `extraction_confidence >= 1.0` get a bucket; anything below competes on rank alone and enters only by out-ranking a diversified pick. The zero-overlap record is now excluded, and the demo record moved to position 5 — which is where `_rank` actually puts it, so the demo now rests on merit rather than on an unearned slot. Verified byte-identical to the plain round-robin when every record is trusted, so **the ablation is untouched**. **B-side closed 2026-07-18, at the C/D↔B merge.** The predicted collision fired exactly as written, and neither author could have caught it: B was authored against a tree with no `extraction_confidence`, so `compress_run` minted at the 1.0 default and `diversify_by_statute` read its own agent's lessons as ground truth. The `statute ""` half never materialised — B mints `§NNN` into `pattern`, so the validator derives a real statute, which made it *worse*: the record owned a sparse real bucket instead of `"?"`. Reproduced before fixing: four trusted §101 records plus one self-generated §112 lesson ranked below all of them returned `['lh-0', 'ep-disc-0001-112-0', 'lh-1', 'lh-2']` — **slot 2 of 4 on provenance, not rank**, evicting a real PTAB record. Fixed by minting at `EPISODE_CONFIDENCE = 0.5` (`agent/episodes.py`), higher than ingest's 0.3 because critiquing a real draft beats an arbitrary untrusted document, still below the trust gate. Two regression tests in `tests/test_episodes.py`, both **verified to fail against the reintroduced bug** — the same standard the D-side hardening used, and the reason this one is recorded as closed rather than reported as closed |
| **`data/distill_loopholes.py` mints `TC####` classes that can never match a CPC disclosure** | Found by review. `_tech_class` returns `f"TC{n}"` (USPTO Technology Center) for every PTAB record it writes, while `_rank`'s highest-order term is `rec.technology_class == disclosure.technology_class` against a CPC class like `G06F`. So every TC-classed record permanently loses that term and is structurally outranked by any CPC-classed one. `agent/distill.py` now raises on TC-shaped input for the *ingest* path, so the two producers disagree on the same field — deliberately, and recorded here rather than reconciled: fixing the ground-truth path rewrites `technology_class` across the corpus the **GPU re-run** measures. Do it immediately after the re-run, not before |
| **Ranking changed, so `agent/memory.py` must be frozen at a recorded SHA when the GPU window opens** | C2 is the last intentional ranking change before the re-run. Record the SHA in this file when the window opens. This board already reports "both live numbers were produced by code that no longer exists" once; the freeze is what stops it reporting it twice |
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
