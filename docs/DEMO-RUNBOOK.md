# Demo runbook (D6)

The three-beat demo — one continuous flow, each beat a track. Runs **offline** today (committed chart + rehearsal modes) so it survives a dead venue network or an unfunded GPU; swap in the live paths below when the endpoint + a HiddenLayer key are up.

**One command:** `bash scripts/demo.sh`

## The three beats

| Beat | Track | Command | Proves |
|---|---|---|---|
| 1 · The learning loop | Recursive Intelligence | `AIRTIGHT_EPISODES_ENABLED=true python -m agent.run_smoke --episodes` (run 2-3x) | past-episode count climbs each run and feeds the next draft: three learning mechanisms (failure library, episodic memory, ingest) compounding live |
| 2 · The poison | HiddenLayer Runtime Security | live: `AIRTIGHT_HL_ENABLED=true ... python -m agent.poison_demo` (or `--fake` backup) | all 5 interaction types analyzed against the real AIDR API; poisoned prior-art doc caught + quarantined on ingest |
| 3 · The wall | NemoClaw + OpenShell | `bash containment/planb/run.sh`, then the live curl below | real socket-level 403 on a Linux kernel, and a real HTTP 403 over the internet at the live URL; the agent knows how and still can't |

Live containment gate, over the internet, no setup:
```
curl -s -X POST https://airtight-openshell.vercel.app/api/gate \
  -H 'content-type: application/json' -d '{"host":"dropbox.com","method":"POST","path":"/upload"}'   # real HTTP 403
```

Close with the vLLM bounty number: **65.2 → 695.8 tok/s, 10.67×** from continuous batching (`docs/THROUGHPUT.md`). Full bounty writeups in `SUBMISSION.md`.

## Live vs rehearsal — what to swap on the day

- **Beat 1 (learning loop):** demo the compounding live. `AIRTIGHT_EPISODES_ENABLED=true python -m agent.run_smoke --episodes` run 2-3 times shows "past episodes" climb 0 to 1 to 2, each retrieved into the next draft. That is the mechanism the track asks for, and it is real. **Do not claim a positive first-vs-last delta.** The controlled ablation, after we fixed a claim-parsing scoring bug that had faked a positive, is `empty 13 / warmed 9` (warmed does not beat empty). Lead with the mechanism and the honesty. If a judge asks about the delta, the story is: we caught a bug that was faking our own win and reported the number that survived it. Framing is in `SUBMISSION.md`.
- **Beat 2 (poison):** `--fake` uses canned HiddenLayer responses (no key). **LIVE-verified 2026-07-18** against the real AIDR API: with `AIRTIGHT_HL_ENABLED=true` + `HIDDENLAYER_CLIENT_ID`/`HIDDENLAYER_CLIENT_SECRET` (drop `--fake`), HiddenLayer flagged the poisoned prior-art doc and all five hops fired through the live bus. Two notes: (1) event keys last **24h**, get a fresh one at the venue (`HIDDENLAYER_ENVIRONMENT=prod-us`); (2) this key's ruleset flags **injection** (the poison beat) but not PII, so the graded **redact** path stays a coded + unit-tested capability, not a live demo. Say "injection detection is live; the redact policy is implemented and tested."
- **Beat 3 (the wall):** **enforcement is now real, lead with it.** `bash containment/planb/run.sh` stands up the four tiers on a stock Linux kernel and returns a real socket-level 403: filing POST hard-denied, Dropbox POST default-denied then operator-rejected, patentsview GET default-denied then operator-approved, data.uspto.gov GET allowed through the gate. The sandbox runs non-root, cap-drop ALL, no-new-privileges, read-only filesystem, with no route off-box except the gate. It is also live at https://airtight-openshell.vercel.app (real HTTP 403 over the internet, operator approve/reject). `python -m containment.demo` is the narrated walkthrough of the same policy. Honest caveat if asked: the NVIDIA vendor `nemoclaw` binary is DGX-gated, so this is the Plan B enforcement path (gVisor/Firecracker-class on a real kernel), which is real containment, not a print.

## Honesty notes to carry on stage (say these, don't hide them)

- Beat 1: the learning **mechanism** is the claim (three compounding sources, live), not a positive delta. The measured delta is `empty 13 / warmed 9` after a scoring-bug fix; we report the number that survived the bug. This is a strength if narrated as rigor, a liability if you claim a win you cannot show.
- Beat 2 is **live-verified** against the real AIDR API. Injection is caught for real; the redact path is implemented + tested but not exercised by this event key's ruleset. Runs in `--fake` rehearsal without a key.
- Beat 3 is **real enforcement**: a real socket-level 403 on a Linux kernel (`containment/planb/`) and live online. The only DGX-gated piece is the NVIDIA vendor binary; the boundary itself holds under a live test.

## Fallbacks

Every beat runs from committed artifacts with `bash scripts/demo.sh` — no network, no GPU, no keys. That is the backup if anything live fails mid-demo. Rehearse it twice.
