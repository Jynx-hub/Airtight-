# GPU re-run runbook — freeze the ranker, measure the ablation

The single highest-leverage open item. Retrieval (`agent/memory.py`) has changed twice
(C1 statute-diversification `d1c60b1`, C2 BM25 `4aa8cee`), so **both live ablation numbers on
the board were produced by code that no longer exists** and neither is quotable. This runbook
turns one warm Modal window into a reproducible measurement.

Read `docs/WORKSTREAMS.md` → "The two headline numbers, stated honestly" before running, so you
know exactly which numbers this replaces.

## Why freeze at all

The harness stamps repo HEAD `git_sha` **and** a content hash of `agent/memory.py`
(`fingerprint.memory_py_sha`, added `agent/eval/harness.py`) into every `results.json`. The
`memory_py_sha` is the hash of the ranker's **on-disk source**, so a run self-documents which
retriever produced it *even if the tree is dirty*. The freeze is the discipline that keeps that
hash meaningful across the window: pin the ranker, record the hash, and don't let anyone edit
`agent/memory.py` mid-run and quietly invalidate the number.

Reference value at time of writing (HEAD `15a54d8`, ranker last changed by `4aa8cee`):

```
agent/memory.py  sha256 = b44efec3682dd217477ce188c7e9085899f4320a14b0d80316b087f5ad66993f
```

If the hash you compute in step 1 differs from this, the ranker moved since 2026-07-18 — that is
fine, just record the new one as the frozen value.

## Steps (run right before Steven un-pauses Modal)

### 1. Pre-flight — clean tree, record the freeze

```bash
cd ~/Airtight-
git fetch origin && git status --short          # must be empty (untracked data/real-eval is not in the import path)
git rev-parse HEAD                               # the frozen commit
python3 -c "import hashlib,pathlib; print(hashlib.sha256(pathlib.Path('agent/memory.py').read_bytes()).hexdigest())"
```

If the tree is dirty, **commit or stash first** — otherwise `git_sha` points at a commit whose
`memory.py` differs from what runs.

### 2. Tag the freeze (immutable pointer)

```bash
SHA=$(git rev-parse --short HEAD)
git tag -a "ablation-freeze-$SHA" -m "memory.py frozen for GPU re-run"
git push origin "ablation-freeze-$SHA"
```

### 3. Announce

Post in the team channel: *"memory.py frozen at `<sha>` for the GPU window — do not touch
`agent/memory.py`, `agent/eval/*`, or the prompt templates until the run lands."* A concurrent
edit is the one thing a tag cannot prevent, and `runtime/bench.py` already warns that a second
session can wake or redeploy the app mid-window. Check `modal app list` shows no other live work.

### 4. Un-pause Modal and run the ablation

Steven un-pauses Modal per `runtime/RUNBOOK.md` (operator's call — the app stays paused by
default; an idle A100 bills against the same fixed credit the demo comes out of). Then, real
generation, pooled over the real 193-record corpus — **not `--fast`**, which is reasoning-off and
for plumbing checks only:

```bash
.venv/bin/python -m agent.eval \
  --data-root data --layout pooled --n 10 --seed 0 \
  --deadline-min 25 \
  --out results/ablation
```

- `--deadline-min` is the credit guard that already saved one burned window — keep it.
- `--seed` makes the holdout reproducible; `--n 10` is the graded holdout size.
- Re-pause Modal the moment the run finishes.

### 5. Verify the number is attributable

The fingerprint must match the freeze — and thanks to `memory_py_sha`, this holds even if the
tree drifted:

```bash
python3 - <<'PY'
import json, glob, os, hashlib, pathlib
f = sorted(glob.glob('results/ablation/*/results.json'), key=os.path.getmtime)[-1]
fp = json.load(open(f))['fingerprint']
live = hashlib.sha256(pathlib.Path('agent/memory.py').read_bytes()).hexdigest()
print("results.json:", f)
print("run  memory_py_sha:", fp['memory_py_sha'])
print("disk memory_py_sha:", live)
print("git_sha:", fp['git_sha'])
print("MATCH" if fp['memory_py_sha'] == live else "MISMATCH — ranker changed mid-window, run is NOT quotable")
PY
```

If it prints `MISMATCH`, something edited the ranker during the window — re-freeze and re-run.

### 6. Record it on the board

Update `docs/WORKSTREAMS.md` in the **same commit** that lands the results:
- the frozen SHA + the `ablation-freeze-*` tag + the `memory_py_sha`
- the `results/ablation/<timestamp>/` path
- the actual delta (empty vs warmed), **replacing** the two stale numbers the board currently
  flags as produced by deleted code
- re-derive the 5/6 headline from the tracked corpus in the same run — the old one ran on
  `data/real-eval/` (see the board's open-risks table)

### 7. After the run

The freeze lifts — `agent/memory.py` is editable again. But note on the board that any subsequent
ranker edit re-opens the "unmeasured live" caveat until the next re-run. The `memory_py_sha` in
the archived `results.json` remains the permanent record of which ranker produced that number.

## Also worth doing in the same window (cheap, while the GPU is warm)

- `data/distill_loopholes.py` mints `TC####` classes that never match a CPC disclosure (open-risks
  table). Fixing it rewrites `technology_class` across the corpus the re-run measures — so do it
  **immediately after** this run, not before, or you invalidate the freeze.
