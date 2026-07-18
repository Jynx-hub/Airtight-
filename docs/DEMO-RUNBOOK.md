# Demo runbook (D6)

The three-beat demo — one continuous flow, each beat a track. Runs **offline** today (committed chart + rehearsal modes) so it survives a dead venue network or an unfunded GPU; swap in the live paths below when the endpoint + a HiddenLayer key are up.

**One command:** `bash scripts/demo.sh`

## The three beats

| Beat | Track | Command | Proves |
|---|---|---|---|
| 1 · Speed-run | Recursive Intelligence | opens the committed ablation chart | same model, empty vs warmed memory → measurably more loopholes caught |
| 2 · The poison | HiddenLayer Runtime Security | `python -m agent.poison_demo --fake` | all 5 interaction types analyzed; the poisoned prior-art doc caught + quarantined on ingest |
| 3 · The wall | NemoClaw + OpenShell | `python -m containment.demo` | file-now hard-denied, exfil default-denied → operator rejects; the agent knows how and still can't |

Close with the vLLM bounty number: **65.2 → 695.8 tok/s, 10.67×** from continuous batching (`docs/THROUGHPUT.md`).

## Live vs rehearsal — what to swap on the day

- **Beat 1 (chart):** the driver shows the newest committed chart. Current committed result: 6 disclosures, warmed on 17 real PTAB loopholes, **warmed wins 5/6** (5/36 → 20/36 loopholes caught).
  ⚠️ **That run is not reproducible as written.** It used `--data-root data/real-eval`, and **`data/real-eval/` no longer exists in the tree** — it was a transient `data/assemble_eval.py` output. For a fresh live run, use the pooled layout over the tracked corpus: warm the endpoint (Steven, `MODAL_MIN_CONTAINERS=1`), then `AIRTIGHT_MODE=live AIRTIGHT_BASE_URL=<modal>/v1 AIRTIGHT_API_KEY=airtight-local AIRTIGHT_MODEL=nemotron python -m agent.eval --data-root data/real --layout pooled --fast --deadline-min 15`. The `--deadline-min` guard keeps it inside the window. Pooled has never produced a `results.json`, and retrieval still ranks without statute (`docs/WORKSTREAMS.md` §C1) — fix C1 before spending the GPU window, or expect a worse number than the committed chart.
- **Beat 2 (poison):** `--fake` uses canned HiddenLayer responses (no key). **LIVE-verified 2026-07-18** against the real AIDR API: with `AIRTIGHT_HL_ENABLED=true` + `HIDDENLAYER_CLIENT_ID`/`HIDDENLAYER_CLIENT_SECRET` (drop `--fake`), HiddenLayer flagged the poisoned prior-art doc as `prompt_injection` (real event_id `0fc717c2-…`) and all five hops fired through the live bus. Two notes: (1) event keys last **24h** — get a fresh one at the venue (`HIDDENLAYER_ENVIRONMENT=prod-us`); (2) this key's ruleset flags **injection** (the poison beat) but not PII, so the graded **redact** path stays a coded + unit-tested capability, not a live demo — say "injection detection is live; the redact policy is implemented and tested."
- **Beat 3 (the wall):** already faithful — `containment/policy.py` reads the real sandbox YAML. It is a **simulation of enforcement** (`openshell_sim.py` prints the gateway flow); the decision logic is real, but there is no live OpenShell sandbox yet (Person 2's F5). If a judge asks, say so — don't imply live Landlock enforcement.

## Honesty notes to carry on stage (say these, don't hide them)

- Beat 1 is warmed on **17** real loopholes, not the 50 in the spec — the chart says so. Disclosures are metadata-only (no abstracts), so drafts are shallow; the *delta* is the claim, not the draft polish.
- Beat 2 is **live-verified** against the real AIDR API — injection is caught for real; the redact path is implemented + tested but not exercised by this event key's ruleset. Runs in `--fake` rehearsal without a key.
- Beat 3 enforces via policy logic + simulation, not a live sandbox.

## Fallbacks

Every beat runs from committed artifacts with `bash scripts/demo.sh` — no network, no GPU, no keys. That is the backup if anything live fails mid-demo. Rehearse it twice.
