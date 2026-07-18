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

- **Beat 1 (chart):** the driver shows the newest committed chart. For a fresh live run, warm the Modal endpoint (Steven, `MODAL_MIN_CONTAINERS=1`), then `AIRTIGHT_MODE=live AIRTIGHT_BASE_URL=<modal>/v1 AIRTIGHT_API_KEY=airtight-local AIRTIGHT_MODEL=nemotron python -m agent.eval --data-root data/real-eval --fast --deadline-min 15`. The `--deadline-min` guard keeps it inside the window. Current committed result: 6 disclosures, warmed on 17 real PTAB loopholes, warmed wins 5/6.
- **Beat 2 (poison):** `--fake` uses canned HiddenLayer responses (no key). **For the real AIDR call**, set `AIRTIGHT_HL_ENABLED=true` + HiddenLayer creds (`HIDDENLAYER_CLIENT_ID`/`SECRET` or `HIDDENLAYER_TOKEN` + `HIDDENLAYER_PROJECT_ID`) and drop `--fake`. **Blocked today: no key.**
- **Beat 3 (the wall):** already faithful — `containment/policy.py` reads the real sandbox YAML. It is a **simulation of enforcement** (`openshell_sim.py` prints the gateway flow); the decision logic is real, but there is no live OpenShell sandbox yet (Person 2's F5). If a judge asks, say so — don't imply live Landlock enforcement.

## Honesty notes to carry on stage (say these, don't hide them)

- Beat 1 is warmed on **17** real loopholes, not the 50 in the spec — the chart says so. Disclosures are metadata-only (no abstracts), so drafts are shallow; the *delta* is the claim, not the draft polish.
- Beat 2 runs against the real SDK but in rehearsal until a HiddenLayer key exists.
- Beat 3 enforces via policy logic + simulation, not a live sandbox.

## Fallbacks

Every beat runs from committed artifacts with `bash scripts/demo.sh` — no network, no GPU, no keys. That is the backup if anything live fails mid-demo. Rehearse it twice.
