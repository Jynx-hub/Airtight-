# data/ — Person 1's lane

Ground truth for the learning loop and the M4 ablation. Tasks E1-E5: `docs/WORKSTREAMS.md`.

**The contract:** everything you produce loads into the shapes in `airtight/shapes.py` — `Disclosure` in, `LoopholeRecord` for every mined edge case. A folder of clean JSON beats a database. `fixtures/sample_disclosure.json` shows the shape; keep real outputs under `data/corpus/`, `data/groundtruth/`, `data/fixtures/`.

Sources (verified 2026-07-17, details in `docs/ARCHITECTURE.md` §Reduction to Practice):
- **USPTO Open Data Portal** — data.uspto.gov (full-text patents; scope to software/electronics CPC classes)
- **PTAB decisions dataset** — data.uspto.gov/ptab/trials/decisions (~25.8k decisions — which claims died and why)
- Google Patents / EPO OPS — read-only prior-art search at draft time

Hard rule: the held-out loophole checklist (E3) must never overlap the warming corpus — keep them in separate files with an overlap check.
