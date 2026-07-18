# Integration status (post-merge map)

*Snapshot after the Runtime + data-groundtruth lanes landed. The point of this
file: one place that says what's canonical, what's superseded, and what debt is
open — so nobody wires against the wrong thing or loses work.*

## Merge state — clean

- **`main` is the integrated superset.** `origin/Runtime` (0 ahead / 42 behind) and `feat/data-groundtruth` (0 ahead / 11 behind) are both **fully merged**; their unique work is on `main`. Those branches are now stale — safe for their owners (Steven, Sreesanth) to delete.
- **Green:** `pytest tests/` → 66 passed, 1 skipped (the skip is the real-pull split test, needs local `data/real`), 0 failures.
- **Demo runs end-to-end:** `bash scripts/demo.sh` drives all three beats offline.

## Canonical vs superseded — wire against the left column

| Concern | **Canonical** | Superseded / parallel | Notes |
|---|---|---|---|
| Model serving | **`runtime/`** (Steven — deployed Modal/vLLM, F1–F4, measured) | `inference/vllm_modal.py`, `inference/verify_endpoint.py`, `inference/RUNBOOK.md` (my pre-deploy sketches) | superseded files are docs/comment-referenced only, no code depends on them; keep `inference/policy/` (F5 OpenShell groundwork) |
| Inference call | **`airtight/doorway.py`** `call_model` (what the agent lane uses) | `runtime/inference_local.py` `chat()` (runtime lane's own) | **two implementations of one hop — the "one boundary" seam.** Both work; consolidation needs Steven's sign-off on which wins |
| Real data | **`data/real/`** (Sreesanth — pooled disclosures/checklists/groundtruth; harness default `--data-root data/real --layout pooled`) | `data/real-eval/` (my distilled-FWD corpus) | two corpora, different provenance (office-action defects vs FWD loopholes) — see the retrieval risk below |
| Ablation harness | **`agent/eval/`** (pooled layout + fixtures layout) | — | one harness, sound; the open variable is retrieval, not the harness |

## Open architectural risks (ranked, with owner)

1. **Statute-blind retrieval — FIXED 2026-07-18 (offline-validated), GPU re-run pending.** `LoopholeRecord` now carries a `statute` (auto-derived from the pattern text), and `retrieve()` diversifies the k across §101/§102/§103/§112 instead of collapsing onto the highest-overlap statute (`agent/memory.py` `diversify_by_statute`). Validated on the real 167-loophole corpus: all 6 graded disclosures now retrieve a statute set that **includes their checklist's statutes** (`statute-match=True`), where before they collapsed onto one — the mechanism behind the backwards run. **Still open:** a GPU re-run of both corpora to confirm the delta itself moves the right way; the retrieval is now sound, the measurement is the last step. Owner: agent lane (Anudeep).
2. **Two-doorway seam.** `airtight/doorway.py` and `runtime/inference_local.py` are parallel clients for the same operator-pinned hop. Not broken, but the "one boundary, three tracks" story has two implementations. Owner: Steven + Anudeep — decide which is canonical, delegate the other to it.
3. **Superseded `inference/` sketches.** Dead-weight confusion risk now that `runtime/` is canonical. Owner: Anudeep — deprecate or delete `inference/{vllm_modal,verify_endpoint,RUNBOOK}` (keep `inference/policy/`).

## What's real vs simulated (say this on stage)

- **Real:** vLLM bounty (10.67× measured), HiddenLayer poison catch (live AIDR, real event id), M4 harness (ran live — delta pending the retrieval fix).
- **Simulated:** OpenShell containment (`containment/` is decision-logic + a printed gateway; real enforcement is P2's F5/F6, not built).

Full demo flow + honesty notes: `docs/DEMO-RUNBOOK.md`. Milestone/ownership detail: `docs/WORKSTREAMS.md`.
