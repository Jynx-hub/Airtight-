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

**How the work splits:** Person 4's shared doorway (with a fake "all clear" stub) goes into `main` on day one, so Persons 1–3 never wait on anyone. Person 1 and Person 2 are fully independent of each other. Person 2's job is front-loaded — once the endpoint is live, they roll onto the OpenShell locks (F5–F7) so Person 4 isn't carrying security alone. On those locks the line is: **Person 2 owns the boundary, Person 4 owns what runs inside it.** P4 hands P2 the list of paths, binaries, and endpoints the agent actually touches; P2 turns that into policy.

---

## Where we actually are (audited 2026-07-18)

Every box below was checked against the code, not against what anyone reported. `[x]` means *verified working*; **◐** means real code exists but the item's defining requirement isn't met yet.

| Lane | Done | Partial | Not started | Reality |
|---|---|---|---|---|
| **1 · Data** (Sreesanth) | **E1–E4** | E5 | — | **50 real G06N patents + 76 real office-action defects on disk**, loading natively into P4's harness. Pulled by `data/pull_uspto.py --groundtruth`; the dead `src/` pipeline is now quarantined under `attic/`. |
| **2 · Inference** (Steven) | **F1–F4** | — | F5a, F5b, F6, F7 | First half fully done and measured. Second half (OpenShell) is a green field — **no `openshell`/`nemoclaw` CLI installed anywhere**. |
| **3 · Surface** | D1, D2, D4 | D3 | D5, D6 | 379 lines total, landed by Anudeep as a starter. **No `feat/surface-*` branch has ever existed.** |
| **4 · Agent** (Anudeep) | **G0** | G1, G2, G3, G4 | G5 | Most-built lane. Everything works **in stub/simulation mode; nothing has touched real infrastructure.** |

**The three things that decide whether this demos:**

1. **G3 is now unblocked — run it.** E1+E2 landed, so the money shot finally has its input: 50 real patents, 38 held-out checklists, 76 real examiner defects, loading into the harness with the leakage guard green. The harness has still **never been run once**. Running it is now the single highest-leverage action on the board, and it needs a live endpoint — the operator un-pauses Modal, runs the ablation, re-pauses. Until that happens the chart that wins the demo does not exist.
2. **D5 + D6 have zero lines and no owner.** The ablation chart is the item this doc calls *"the picture that wins the demo"*, and the demo script that stitches the beats doesn't exist. Both are downstream of #1 anyway.
3. **Nothing is actually contained yet.** `containment/` is a self-declared simulation (`openshell_sim.py:6`: *"This is presentation, not enforcement"*) — the 403 is a `print()`. F5a is the binary go/no-go that unblocks F5b–F7, G1's sandbox requirement, and G5.

**Two cross-lane facts worth naming:** Anudeep has been covering three lanes (agent + the surface starter + the one working USPTO puller), and Person 3 has never committed to this repo. Commit counts: Steven 20, Anudeep 12, Sreesanth 2.

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

> **Status (updated 2026-07-18, after the first real ODP pull):** ✅ **E1–E4 done — the lane's critical-path risk is closed.** `data/real/` now holds **50 real granted G06N patents** with real abstracts and real claims, **38 held-out checklists**, and **76 loopholes mined from actual examiner office actions** — §103 ×44, §101 ×11, §112 ×18, §102 ×3, which is exactly the software-patent failure profile `CLAUDE.md` scopes this project to. Verified end to end, not just written: Person 4's own `load_disclosures` / `load_checklist` read the layout natively and `assert_no_overlap` passes at **0 id collisions, 0 Jaccard flags**. Built on Anudeep's `data/pull_uspto.py`, extended with a `--groundtruth` mode.
>
> ⚠️ **`data/` is gitignored — pulling `main` does not get you this data.** Everyone runs it themselves: register a free key at https://data.uspto.gov, then `USPTO_API_KEY=... python -m data.pull_uspto --groundtruth --cpc G06N --limit 50` (~5 min, rate-limited on purpose). No key, no pull — the puller never fabricates.
>
> **The `src/` pipeline (`01f4daf`) was not repaired, and is not on the path.** It still targets retired endpoints (`config.py:28` PEDS, `config.py:36` PatentsView, `src/clients/ptab_client.py:37` ptabdata) and still speaks a non-matching `Disclosure` schema (`src/fixture_builder.py:44` vs `airtight/shapes.py:11`). All three dead endpoints were superseded by the one ODP host `api.uspto.gov/api/v1` that the working puller already speaks, so porting them would have arrived where we already are. Treat it as dead weight to quarantine, not a base to build on.
>
> **✅ Done — quarantined under `attic/`.** Two corrections to the audit above, both verified before the move. (a) It is **3,112 lines** in `src/`, not 4,500 (4,176 counting the eight scripts, which moved too). (b) `tests/test_extractor.py` contributed **23 of the 71 passing tests**, so a blind delete would have silently broken the documented suite count — the tests moved with the code they cover and the baseline is now **48 passed**. Root `config.py` moved as well: `oa_extractor.py` reads four regex tables from it and no working-path module imports it. Rescue paths for the two offline-clean files are in `attic/README.md`.
>
> ⚠️ Two scripts fabricate data rather than fetch it, and would poison the benchmark if anyone ran them believing otherwise: `scripts/fetch_50k.py:133-158` clones **one** hardcoded record 50,000 times with incremented IDs, tagged `"source": "hupd_synthetic"` — it would fill `data/corpus/patents/` and look like a successful pull; and `src/extractors/groundtruth_builder.py:126` derives fake PTAB outcomes from an MD5 hash with a hardcoded rationale. Delete or clearly quarantine both. **✅ Done** — both moved to `attic/` (`attic/scripts/fetch_50k.py`, `attic/src/extractors/groundtruth_builder.py`) and neither is reachable from the working path.

- [x] **E1** `feat/data-corpus` — Pull full-text granted patents from the USPTO Open Data Portal for the 2-3 CPC classes we pick. Target: a clean warming set of **~50 same-class patents** plus a few hundred more for ingest.
  **Done — 50 patents on disk, with real invention text.** `data/real/disclosures/` holds 50 granted G06N applications, each a valid `Disclosure` carrying a **real abstract** (~1.5k chars) and its **real claims** (~12k chars) — not the metadata boilerplate the thin `--patents` path produces. The search endpoint exposes no abstract at all, so the puller walks the file wrapper, where `ABST` and `CLM` are separate documents downloadable as a tar of ST.96 XML. Records are constrained to granted `REGULAR` applications carrying a real CPC, and anything unclassifiable is dropped rather than guessed at. **Scope still open:** this is **one** CPC class, not the 2-3 named here (`--cpc G06F`, `--cpc H04L` are the same command), and the "few hundred more for ingest" has not been pulled.
- [x] **E2** `feat/data-groundtruth` — Pull the **PTAB decisions dataset** + office-action rejections. For each patent in our classes: *which claims died, and why.* This is the scoring key for everything.
  **Done — 76 defects mined from real examiner office actions.** For each application the puller fetches its `CTNF`/`CTFR` rejection and parses the formal rejection statement — *"Claims 1-5, 8, 10-14, 17, and 19-20 are rejected under 35 U.S.C. 103 as being unpatentable over Mohammed et al (US 2025/0348732) in view of Rubin (US 2018/0095935)"* — which yields the claim numbers, the statute and the cited prior art in one sentence, then resolves those numbers to real claim text from `CLM`. Out to `data/real/groundtruth/loopholes.json`: **§103 ×44, §101 ×11** (Alice/Mayo abstract-idea, the dominant software rejection), **§112 ×18** (indefiniteness, antecedent-basis, written description, enablement), **§102 ×3**.
  **Route changed, deliberately:** office actions, *not* the PTAB decisions dataset — an OA names the claim, the statute and the prior art in a single fixed grammar, which PTAB trial metadata does not. `--ptab` still emits raw records and `distill_loopholes.py` still does not exist; that leg is now **redundant rather than blocking**.
  ⚠️ **`oa_extractor.py` is not on the path, and is now quarantined** at `attic/src/extractors/oa_extractor.py` — a correction to the earlier audit, which recommended salvaging it. Its 23/23 tests passed against a clean synthetic fixture, but its rationale windows centre on marker words, so on real office actions they land on the obviousness *reasoning* ("It would have been obvious to one of ordinary skill…") and never contain the claim list. It produced claim shapes like `"(Canceled) Canceled 3"` and *"Determining the scope and contents of the prior art"* (Graham v. Deere boilerplate, not a claim). Its 23 tests moved with it (`attic/test_extractor.py`), taking the suite baseline 71 → 48; the pooled-layout tests then brought it to **55 passed, 1 skipped** (56 with a local `data/real/` pull).
- [x] **E3** `feat/data-fixtures` — Build the **fixed disclosure set**: 3-5 invention write-ups (in the agreed Disclosure shape) used in every eval run, each with a **held-out loophole checklist** derived from E2 that the robot is graded against. Never let the checklist leak into the warming data.
  **Done — 38 held-out checklists, and unlike the placeholders these *are* derived from E2.** `data/real/checklists/{disclosure_id}.json`, one per disclosure that actually drew a rejection, well past the 3-5 target. Each grades against the real claim the examiner rejected and the real ground they rejected it on. The 2 hand-written fixtures (`disc-0001`, `disc-0002`) remain and are still consumed by `tests/test_episodes.py:16` and `tests/test_subagents.py:18` — keep them; they are the offline/stub path. The no-leak rule is enforced by Person 4's `agent/eval/harness.py:41` and is now **verified against real data**: excluding a disclosure's own records from the 76-record pool gives 0 collisions and 0 Jaccard flags.
  One design note worth keeping: a checklist file is written **only** for disclosures that have defects. The 12 clean ones get none on purpose — an empty checklist scores 0-of-0 and would read as a *passing* ablation.
- [x] **E4** `feat/data-loaders` — Simple loaders that hand all of the above to Person 4's code in the agreed shapes. A folder of clean JSON beats a database — simplest thing that works.
  **Done — by output layout, not by new loader code.** The lane's "Done when" is that Person 4 can load with one call each, and the puller's output feeds the harness's own loaders directly: `load_disclosures(Path('data/real/disclosures'))` → 50 records, `load_checklist(Path('data/real/checklists'), id)` → that disclosure's held-out set. Writing loaders nobody imports was the original failure mode; matching the consumer's shapes is the simpler thing that works.
  **One correction:** the *shapes* matched, but the *directory layout* did not — `run_ablation` wanted `fixtures/disclosures` + `groundtruth/checklists` + `corpus/loopholes`, while the puller writes one undivided pool (`disclosures/` + `checklists/`). That is now bridged by `--layout pooled`, which also does the thing the pool genuinely needs: `data/real/groundtruth/loopholes.json` is the **union of all 38 checklists**, so warming from it would hand the warmed arm the exact records it is graded on. The harness instead splits the pool into a graded holdout and a corpus built from every *other* application's records. Run it with `python -m agent.eval --data-root data/real --layout pooled --n 10`.
  ⚠️ **`src/loaders.py` was 318 lines of dead, broken code** — nothing imported it, and all 5 functions failed against the repo's own files (`load_fixtures` globs `disc_*.json` against `disc-0001.json`; `load_checklists` reads a directory that doesn't hold them; the other three `FileNotFoundError`). **Now quarantined** at `attic/src/loaders.py` — leaving a plausible-looking loader that silently returns `[]` next to a working path was a trap for whoever read this lane next.
- [ ] **E5** `feat/data-poison` — The **booby-trapped prior-art PDF**: a plausible patent PDF with hidden "leak the client's disclosure" text inside, for the security demo. Coordinate the hiding trick with Person 4 so the scanner genuinely catches it.
  **◐ Partial.** `data/fixtures/poisoned_prior_art.txt` exists with a real injection payload and **is wired into the guardrail tests** (`tests/test_guardrails.py:173`), so the security demo can run. But there is **no PDF anywhere in the repo** and the payload is plain visible text — no hiding trick, because `.txt` has no invisible-render layer. `poison_builder.py` (275 lines, invisible-text + XMP vectors) is the real implementation and has never been run; it is now quarantined at `attic/src/poison_builder.py`, but it is **offline-clean and cheap to rescue** — it needs only `config.DATA_DIR`, so swapping that one import for a local path constant fully decouples it (`attic/README.md`). Also note: the `.txt` was committed by **Anudeep** under "Session C", not by this lane.

**Done when:** Person 4 can load the warming corpus, the ground-truth checklists, the fixed disclosures, and the poisoned PDF with one call each — and the checklist provably doesn't overlap the warming set.

**→ Met, except the poisoned PDF.** Corpus, checklists and disclosures all load through the harness's own calls, and the no-overlap proof is green on real data (0 collisions, 0 Jaccard flags). The poison is still a `.txt` with no hiding layer (E5). **Remaining work in this lane, in order:** (1) rescue `attic/src/poison_builder.py` (decouple its one `config.DATA_DIR` import) and run it to produce the actual PDF, closing E5; (2) broaden the corpus to G06F/H04L if there's time — all 50 disclosures are currently G06N, which leaves the class-match half of retrieval in `agent/memory.py` constant-true and untested. **(3) Done:** the whole `src/` tree, root `config.py` and the eight scripts that drove them are quarantined under `attic/` — see `attic/README.md` for why and for the two rescue paths.

---

## Person 2 · Inference — the brain hosting · `lane/inference`

**Your job:** Stand up the AI brain everyone else calls, then help lock the doors. Your first job (F1-F4) is **M1b** and the **$500 vLLM bounty** — it's front-loaded, so plan to finish it early and roll onto the second half. Serving detail: `research/vllm.md` · wiring: `docs/INFERENCE-LOCAL.md`.

> **Status (2026-07-18):** ✅ **F1 + F2 done** — Nemotron 3 Nano deployed on vLLM to Modal's free tier, `inference.local` live, and the concurrent-batching numbers are on record: **10.67× aggregate throughput (65.2 → 695.8 tok/s)** with the curve kneeing at C=16 exactly where `--max-num-seqs 16` is pinned. That's **M1b** plus the $500 bounty evidence (`docs/THROUGHPUT.md`). ✅ **F3 done** too — one-var `INFERENCE_BACKEND` flip, all three backends (legacy/modal/nim) verified green end-to-end. ✅ **F4 done** — `runtime/RUNBOOK.md` is the team handoff (consumer quickstart + five-line demo-day card + NIM flip), and the re-benchmark it triggered changed the demo plan: the judged profile is now **`a100-bf16`**, because `l40s-fp8` — faster and cheaper to run — needs **~12 min** to cold start vs the A100's ~1–2, and Modal preempts containers. The documented "~2–5 min cold start" was wrong. **That closes M1b and the whole first half of this lane.** **Next:** the OpenShell locks, starting with **F5a**: a sandbox has to exist on hosted DGX Spark before F5b–F7 have anything to attach to.

### First: the endpoint (M1b + the $500 vLLM bounty)
- [x] **F1** `feat/inference-modal` — Deploy **Nemotron 3 Nano** on vLLM to **Modal's free tier** (`modal deploy runtime/modal_app.py`). **L40S + FP8** is the guaranteed fit; weights cached in a Modal Volume, HF token as a Modal Secret. Scale-to-zero for dev — you only burn credits while a request is running. (Serve **Super** only if you later land a bigger box; don't burn hours on it.)
- [x] **F2** `feat/inference-verify` — Prove the Modal endpoint is OpenAI-compatible (chat + streaming), then **load-test it with concurrent requests** and write down the throughput numbers. Continuous batching under concurrent load is exactly what the $500 bounty judges — a real before/after number is gold. → **`docs/THROUGHPUT.md`: 65.2 → 695.8 tok/s = 10.67× from continuous batching**, curve knees at C=16 exactly where `--max-num-seqs 16` is pinned. Harness `runtime/bench.py`, raw JSON in `runtime/bench-results/`. Found en route: the streaming path mislabels all output as `reasoning_content` (see THROUGHPUT.md §Open issue) — bites the Surface lane's streaming UI, not blocking F2.
- [x] **F3** `feat/inference-routing` — Point `inference.local` → the **Modal URL** (creds host-side, never in the sandbox), and set the **NVIDIA NIM free dev endpoint** as the fallback so **one env flip** swaps backends if Modal is cold or credits run out. → **Done.** The flip is the single var `INFERENCE_BACKEND=modal|nim`; both credential sets coexist so flipping never destroys the other key (the old three-var flip overwrote `INFERENCE_API_KEY` with the nvapi key). **All three backends verified green end-to-end** — legacy, modal, and nim — each passing models + chat + tool-call, and the doorway's `chat()` runs unchanged across them (both reasoning modes; NIM accepts `chat_template_kwargs` with no 400). Prove it any time: `bash runtime/serve-nim.sh`. Fixed en route: `verify.sh` sourced `.env` in a way that *overwrote* exported vars, so `INFERENCE_BACKEND=nim bash verify.sh` would have silently tested Modal and passed — a green check proving nothing. No automatic failover by design (a silent hop to hosted NIM would void the bounty evidence). Two honest gaps recorded in `docs/INFERENCE-LOCAL.md`: `inference.local` is still a naming contract with no gateway process, and creds are still read inside the sandbox — both close at F5.
- [x] **F4** `feat/inference-runbook` — Hand the team one base URL + model name via the secrets file. Write the 5-line "keep it warm for the demo / flip to NIM" runbook, and own keeping the endpoint alive through judging (`min_containers=1` for the show). → **Done.** `runtime/RUNBOOK.md` is the handoff: a consumer quickstart that explicitly needs **no Modal account, no CLI, no `HF_TOKEN`** (deployer-only — that split existed nowhere before), the five-line demo-day card, the NIM flip with its 40 req/min ceiling, and the known surprises so streaming's empty `content` doesn't read as a bug. Base URL stays **out of the public repo** and is handed out of band; `.env.example` gained the vars the doorway actually reads (`MODAL_BASE_URL`/`MODAL_MODEL`/`MODAL_API_KEY`, `INFERENCE_TIMEOUT`) — verified `MODAL_BASE_URL` really does win over `INFERENCE_BASE_URL`. **Found en route, and it changed the demo plan:** the `l40s-fp8` profile everything documented as "the default" is genuinely faster *and* cheaper (865 vs 696 tok/s at C=16, $1.95 vs $2.50/hr) but its vLLM `init engine` takes **494–602s vs the A100's 29s**, so a cold start is **~12 min, not ~2–5** — measured twice, with weights *and* compile cache warm. Modal preempted a container the same session, so the judged profile is now pinned to **`a100-bf16` for recovery time**, and the ~2–5 min cold-start figure in the docs was simply wrong. L40S numbers kept as corroboration: batching holds at 9.4–11× across two GPUs, two precisions, two attention backends. Cost of the window: ~$1.20, now logged in the new `docs/COSTS.md` spend ledger.

### Then: the locked doors (M5)

**Nothing here is started.** No `openshell`/`nemoclaw` CLI is installed anywhere yet and there is no policy YAML in the repo — F5–F7 are a green field, not a polish pass.

**Who owns what in this block:**

| | Person 2 (owner) | Person 4 (supplies / consumes) |
|---|---|---|
| **F5a** host standup | does all of it | — |
| **F5b** the four locks | writes + applies the policy | hands P2 the agent's real touch-list (paths, binaries, endpoints) |
| **F6** the gradient | writes the rule tiers, runs the operator side of approvals | agent must read the Policy Advisor skill and submit proposals (G1) |
| **F7** audit → enforce | runs the sweep, reads the logs, flips to enforce | agent has to actually *run* for there to be anything to observe |

Person 2 owns the boundary; Person 4 owns the thing inside it. The handoff in both directions is a list of what the agent touches — get that written down early, it's the whole input to F5b.

> ⚠️ **Read before starting: you need a Linux host, and it isn't your laptop.** OpenShell's containment is Linux **Landlock LSM + seccomp-BPF + namespaces** — it cannot run natively on macOS (`docs/BUILD-PLAN.md` §Deployment decision). The standing decision is **hosted DGX Spark** (`build.nvidia.com/spark/nemoclaw`), never local and never venue hardware. Until a sandbox exists there, F5b–F7 have nothing to attach to.

- [ ] **F5a** `feat/inference-sandbox` — **Prerequisite, do this first.** Get `nemoclaw onboard` to complete on **hosted DGX Spark** and shell in (`nemoclaw <name> connect`). Deliverable is small and binary: a named sandbox you can enter. If the early preview won't stand up, fall back to `research/nemoclaw-openshell.md` §8 (gVisor/Firecracker + OPA/Rego + a NIM proxy) on a **remote** Linux host, described in the same four-tier vocabulary — the fallback stays non-local too.
- [ ] **F5b** `feat/inference-openshell` — One policy YAML in the repo covering all four enforcement tiers. Schema-accurate shape: `research/nemoclaw-openshell.md` §3 and §5.

  | Tier | What to pin | Mutability |
  |---|---|---|
  | Filesystem | `read_write: [/sandbox, /tmp]`, everything else read-only; disclosures mounted read-only | static — locked at creation |
  | Process | `run_as_user: agent` — never root/0 | static |
  | Network | egress allowlist, per-binary; needs **two** inference destinations (Modal *and* NIM), not one | dynamic, hot-reload |
  | Inference | an `inference.local` endpoint entry at `enforcement: enforce` | dynamic, hot-reload |

  **F5b is also where the two honest gaps close** (both written down in `docs/INFERENCE-LOCAL.md` §Known gaps so nobody claims them early):
  - `inference.local` becomes a **real resolvable host with a gateway process** in front of it, instead of a naming contract that resolves to the operator-pinned Modal URL in `runtime/.env`.
  - **Credentials move host-side.** Today `runtime/inference_local.py` reads the API key from inside the sandbox, so "creds never in the sandbox" is currently *false*. The gateway has to inject them and the sandbox has to hold none. ← **this is the real engineering in F5b, not the YAML.**
- [ ] **F6** `feat/inference-gradient` — Three levels, not one blunt "no". Note this is **a flow, not a YAML key** — there is no `require_approval:` (`research/nemoclaw-openshell.md` §4):
  - **Tier 1 · auto-allow** — reversible reads and searches match an `allow` rule and just go.
  - **Tier 3 · hard-deny** — `deny_rules` for the truly-never: actually filing, repo deletion, branch-protection changes.
  - **Tier 2 · escalate to a human** — everything else falls through default-deny into **Policy Advisor**: `403` with `agent_guidance` → agent reads `/etc/openshell/skills/policy_advisor.md` → `POST /v1/proposals` (an `addRule` op) via `policy.local` → operator runs `openshell rule approve|reject <sandbox> --chunk-id <id>` **from outside the sandbox** → hot-reload → agent retries.

  Rehearse the answer to *"isn't `enforcement: audit` your approval gate?"* — **no.** Audit logs violations and **lets the traffic through**; it is a discovery mode, not a gate. Judges are expected to probe exactly this distinction.
- [ ] **F7** `feat/inference-audit` — Set `enforcement: audit` on every endpoint, run the full agent flow end to end, and capture what it actually *tries* (`openshell logs <name> --tail --source sandbox`). Then flip to `enforce` for the judged run. **This is the pass that catches the door nobody thought of** — "a policy judges break via an un-covered egress path" is the named top risk on this track (`docs/BUILD-PLAN.md` scorecard). Depends on Person 4's agent being runnable (G1, ideally G2) — you cannot observe the egress of an agent that doesn't exist yet, so schedule F7 after their loop is alive.

**Done when:** everyone's calls hit a real vLLM-served Nemotron through `inference.local` with concurrency numbers on record — and the trick prompt *"file now + back up to Dropbox"* gets hard-blocked by policy you set. That prompt is the acceptance test for this whole block: **Dropbox** = un-allowlisted egress (F5b), **filing** = `deny_rules` (F6). It's also Person 3's demo beat *"the wall"* in D6 — so F6 landing is what unblocks their rehearsal.

---

## Person 3 · Surface — the screen + the show · `lane/surface`

**Your job:** Build the thing judges actually click (type an idea → get a patent), and run the live demo that shows off everything in one smooth flow. Build every screen against **fake sample data first** so you're never waiting on anyone.

> **Status (audited 2026-07-18):** ⚠️ **Nobody is currently building this lane.** The whole surface is **4 files, 379 lines**, landed as a starter by **Anudeep** (`a51b4bf`) while covering for the lane — **no `feat/surface-*` branch has ever existed** and Person 3 has not committed to this repo. The click-through half genuinely works (idea → draft → patent, against the real agent loop). The *show* half — D5 and D6, the two items that carry the demo — has **zero lines written**. No Next.js, no React, no Streamlit anywhere: one hand-written static HTML file with vanilla JS.

### The screen
- [x] **D1** `feat/surface-backend` — The thin connector that hands requests to the robot and answers back. Keep it thin — the robot is the star. → **Done, and genuinely wired** — `surface/app.py:19` imports `draft_patent` and `:66` calls it for real; security findings come off the live guardrails bus (`:67-72`). Not mocked. *(Caveat: `g.AUDIT_LOG` is read as a module global after the draft, so concurrent requests would cross-attribute findings — fine for a demo, wrong under load.)*
- [x] **D2** `feat/surface-intake` — The intake screen: a few simple questions that capture the invention. *(Default: Next.js. Streamlit is the faster backup if time's tight.)* → **Done — a human can actually click it.** Real form at `surface/static/index.html:75-90`, served at `/`, with sample-prefill wired to `/api/sample`. **Stack deviates:** neither Next.js nor Streamlit — one static HTML file with inline CSS and vanilla JS. Functionally satisfies the item; architecturally there's no build step or component structure to grow into.
- [ ] **D3** `feat/surface-studio` — The review screen: read the draft, tweak it.
  **◐ Partial — and the most misleading item on the board, because it demos as working.** Claims render into editable `<textarea>`s (`index.html:161-169`), but **the edits go nowhere**: no change handler, no save button, no local state, and no route that accepts a modified `Draft` — `/api/draft` only ever accepts a `Disclosure`. A user can type into the boxes and their edits are silently discarded. "Read the draft" is done; "tweak it" is a text box that looks interactive and isn't.
- [x] **D4** `feat/surface-grant` — The final screen: finished patent **plus** the loophole report (security catches + smart catches). → **Done.** All four blocks render (`index.html:99-118`): specification, smart catches, loopholes pre-empted from memory, runtime security findings. Notably honest — when HiddenLayer is off it says so rather than faking a clean scan (`index.html:180-182`). *(No export/download; the patent is a raw text dump. Literal checklist is met.)*
- [ ] **D5** `feat/surface-chart` — The **ablation chart view**: empty-memory vs trained-memory, side by side, from Person 4's EvalResult output. **This is the picture that wins the demo — make it unmissable.**
  **Not started — zero lines, and no input data either.** Grep for `chart|ablation|eval` across `surface/` returns **no hits**. ⚠️ **Don't mistake `chart.html` for this being done:** that file is emitted by *Person 4's* harness (`agent/eval/harness.py:190`) and its own docstring calls itself "the zero-dependency fallback... Person 3's D5 view consumes `results.json`" (`agent/eval/chart.py:3-4`). No surface route serves it, and `results/ablation/` doesn't exist yet because G3 has never been run.

### The live show
- [ ] **D6** `feat/demo-runbook` — Stitch the moments into one script: **the glow-up** (ablation chart), **the trap** (poisoned PDF caught on ingest), **the wall** (file-and-exfil prompt blocked live), and the optional **whitespace** beat only if everything else is green. **Rehearse at least twice**; pre-record a backup for every live call.
  **Not started — zero lines.** No demo script exists anywhere in `docs/`. ⚠️ **`runtime/RUNBOOK.md` is not this** — that's Person 2's *inference* runbook, a different artifact. Three of the four beats exist as separate executables owned by *other* lanes (the wall → `containment/demo.py`, the trap → `agent/ingest.py --fake-detect`, the glow-up → the eval harness) and the whitespace beat has no code path at all. Nothing stitches them. No rehearsals, no pre-recorded backups.

**Done when:** someone can click idea → draft → patent, and the show runs start to finish without a hitch.

---

## Person 4 · Anudeep — the robot itself · `lane/agent`

**Your job:** The agent, its memory, its security bus, and the proof it gets smarter. This is the **critical path** — the Claude Code kickoff prompts in `docs/SESSIONS.md` are your per-milestone scripts. Ship the shared doorway stub to `main` first so nobody waits on you.

> **Status (audited 2026-07-18):** **The most-built lane — and the most honest.** Everything on this list exists as tested code, and the lane consistently refuses to overclaim: stub mode won't fabricate an ablation delta, `UNVERIFIED` markers sit on the exact lines needing re-verification, and the containment sim banners itself on every run. The gap is uniform and has one shape: **everything is built and tested in stub/simulation mode; nothing here has touched real infrastructure.** Live vLLM (G3), real HiddenLayer (G4), and actual OpenShell (G1, G5) are all absent — and two of those three are blocked on P2. Anudeep also covered work outside this lane: the surface starter (D1/D2/D4) and the one working USPTO puller.

- [x] **G0** `feat/agent-doorway` — The shared inference doorway (stubbed "all clear"), into `main` day one. Contract: `docs/INFERENCE-LOCAL.md`. → **Done**, and it holds. Single entry point (`airtight/doorway.py:58`), `AIRTIGHT_MODE` defaults to `stub` so a fresh clone runs with no network, and the "no other model client" rule is *enforced*, not just documented — `tests/test_smoke.py:22` makes constructing a client in stub mode a hard test failure. Landed day one in `6a27c65`.
- [ ] **G1** `feat/agent-core` — The work loop: plan → draft → self-critique → hand back, running in the OpenShell sandbox (hosted, never local), every call through the doorway. Needs P2's **F5a** sandbox to exist; in return, **write down every path, binary, and endpoint your loop touches and hand it to P2** — that list is the entire input to their F5b policy. The loop also has to read the Policy Advisor skill and submit `addRule` proposals when it hits a 403, or P2's F6 escalation tier has no agent side. *(Session A, M1)*
  **◐ Partial.** The loop is real and tested end to end — plan/draft/critique at `agent/loop.py:81-90`, every turn through the doorway. But both distinguishing requirements are unmet: (1) **it runs as ordinary local Python, not in a sandbox** — no sandbox invocation exists anywhere, and F5a hasn't landed to run in; (2) **there is no agent-side Policy Advisor code at all** — no 403 handling, no `addRule` POST, never reads `policy_advisor.md`. The touch-list handoff to P2 partly exists (`docs/ARCHITECTURE.md:195` + `inference/policy/airtight-sandbox.yaml`). **The 403/addRule client is the one item in this lane that is unbuilt *and* unblocked** — it can be written against a mock today, and without it P2's F6 has no counterpart when it lands.
- [ ] **G2** `feat/agent-memory` — The learning: ingest Person 1's corpus into the edge-case store (simplest store that answers "5 most relevant past mistakes for this kind of invention"), RAG-from-self into the drafting prompt, save a lesson after every draft. *(M3)*
  **◐ Partial — closest to done.** All four sub-parts have working, tested code: `retrieve(disclosure, k=5)` (`agent/memory.py:41`), RAG into the draft/critique prompts (`agent/loop.py:64`), lesson-write via `compress_run()` (`agent/episodes.py:38`). Two gaps: it still ingests **6 hand-written fixture records rather than Person 1's corpus** — which now exists (76 real office-action defects, E2), so this is a wiring job, not a blocked one — and "after every draft" is **off by default** — `AIRTIGHT_EPISODES_ENABLED=false` (`airtight/config.py:34`), and `memory/episodes/` is empty, so no lesson has ever actually been saved.
- [ ] **G3** `feat/agent-eval` — The **money shot**: the eval harness on Person 1's fixtures — same invention, same model, same prompt, memory empty vs warmed on 50 patents; three metrics (loopholes caught ▲, time ▼, defects ▼); EvalResult out to Person 3's chart. *(Session B, M4 — protect this above everything)*
  **◐ Partial — BUILT, never RUN.** The harness is the highest-quality code in the repo and exceeds the spec: paired back-to-back runs (`harness.py:175`), a `scaffold_proof()` asserting both conditions render byte-identical templates outside the memory slot (`:64`), a hard train/test leakage guard (`:43`), a config fingerprint with git SHA + prompt hashes (`:81`), and a blinded judge that downgrades any "closed" verdict whose quoted evidence isn't literally in the claims (`judge.py:88`). **Four independent confirmations it hasn't run:** no `results/ablation/` exists; `results/` is gitignored so output was never going to be committed; the two files in `results/security/` are leaked pytest artifacts (all carry `"event_id": "e"`, the canned value from `tests/test_containment.py:73`); and the fixture set is **2 disclosures, not 50 patents**. In stub mode the delta is **zero by construction** (`judge.py:81`) — `tests/test_eval.py:75` asserts exactly that. Honest, but it means the passing test proves plumbing, not that memory helps.
  ✅ **The P1 gap that blocked this is closed.** "Memory empty vs warmed on 50 patents" now has its 50 patents: `data/real/disclosures` (50), `data/real/checklists` (38 held-out), `data/real/groundtruth/loopholes.json` (76 defects from real office actions). The harness's own loaders read them and `assert_no_overlap` passes at 0 collisions, so the warmed arm would retrieve from **real examiner rejections**, not 6 hand-written notes. Two things still stand between here and a chart: the data is **gitignored, so pull it yourself** (E1 status block has the command), and **stub mode still gives a zero delta by construction** (`judge.py:81`) — this has to run against the live endpoint, which means the operator un-pausing Modal for the window.
- [ ] **G4** `feat/agent-guardrails` — The security bus: HiddenLayer scanning on **all five** hops (user input, robot output, tool asks, tool answers, **documents it reads**), graded responses (pass / redact / quarantine / block+alert), fail-closed on the risky two. *(Session C, M2)*
  **◐ Partial.** Policy logic is complete and well-tested: all five hops, all four graded actions, and fail-closed on exactly the risky two (`TOOL_CALL`, `INGESTED_DOCUMENT` — `airtight/guardrails.py:82,84`), with `tests/test_guardrails.py:131,138` proving open-vs-closed behaviour. Three caveats against "all five hops wired": **only 3 of 5 fire in the agent's real path** — `USER_PROMPT`/`MODEL_RESPONSE` at `doorway.py:40,43` and `INGESTED_DOCUMENT` in the separate `agent/ingest.py` CLI; the two tool hops exist as a `guarded_tool` decorator that **no agent tool uses**, because the loop has no tools to wrap. **HiddenLayer is off by default** (`config.py:24`) and returns `PASS` with `mode="off"`, so a default clone scans nothing. And the **SDK isn't installed** — `_raw_analyze()` has never executed; every test monkeypatches it, and `guardrails.py:117` flags the endpoint shape as `UNVERIFIED`.
- [ ] **G5** `feat/agent-adversarial` — With Persons 1 & 2: the poisoned-PDF catch and the "file now + Dropbox" wall, wired end to end for the demo. The wall is **P2's policy doing the blocking** (F5b un-allowlisted egress + F6 `deny_rules`), not your code — your part is the agent genuinely attempting it and surfacing the refusal. Blocked until F6 lands. *(Session D, M6)*
  **Not started as specified — and mind the wording.** `containment/` is a **simulation, not enforcement**, and says so itself (`containment/openshell_sim.py:6`: *"This is presentation, not enforcement"*). The "403" is a `print()` (`openshell_sim.py:29`); `attempt_egress()` never opens a socket. Against this item's own wording — *"the wall is P2's policy doing the blocking, not your code"* — today's implementation is the **exact inverse**: all blocking is agent-repo Python, with no P2 enforcement layer to defer to. Correctly blocked (F6 hasn't landed; F5 hasn't either). **Partial credit that should survive:** the decisions are genuinely data-driven, parsing the real `inference/policy/airtight-sandbox.yaml` — `tests/test_containment.py:45` edits a `deny_rule` in a temp copy and shows the verdict flip. That logic should port straight onto real OpenShell.

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
| 2 | The NemoClaw/OpenShell early preview won't stand up (F5a), leaving F5b–F7 with nothing to attach to | Attempt `nemoclaw onboard` on **hosted DGX Spark early** — it's a small binary go/no-go, so fail fast rather than at the venue; fallback is `research/nemoclaw-openshell.md` §8 (gVisor/Firecracker + OPA/Rego + NIM proxy) on a remote Linux host, presented in the same four-tier vocabulary |
| 2 | Judges find an egress path the policy never covered | That's exactly what **F7** is for — audit-mode sweep of the *real* agent first, read the denial logs, then flip to enforce. Don't skip it to save time; it's the pass that catches the door nobody thought of |
| 3 | A live internet call glitches mid-demo | Every moment has a pre-recorded backup; rehearse twice |
| 4 | One person owning agent + memory + security + eval is too much | The stub-first doorway means nothing blocks on you; P2 takes the OpenShell locks; if still tight, P1 co-owns eval scoring (they built the checklist) and M6 polish gets cut before M4 does |

---

*Keep this current — tick the boxes as things get done. This is the team's to-do list of record.*

*Convention, set by the 2026-07-18 audit: **`[x]` means verified against the code**, not self-reported. **◐ Partial** means real code exists but the item's defining requirement isn't met — read the note for what's missing before assuming it's nearly done. Several items looked done by filename and were not, so tick from evidence.*
