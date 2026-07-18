# surface/ — Person 3's lane

The Applicant Surface (intake → draft studio → grant + loophole report) and the demo show. Tasks D1-D6: `docs/WORKSTREAMS.md`.

**A working starter is here** — thin but clickable end to end, the way `inference/vllm_modal.py` starts Person 2. Make it pretty (or throw a Next.js frontend at the JSON API below); the contract is defined so your work isn't wasted.

## Run it

```bash
pip install -e ".[web]"
uvicorn surface.app:app --reload      # open http://localhost:8000
```

Works in stub mode with no network. Set `AIRTIGHT_MODE=live` (+ Person 2's Modal URL) for real drafts.

## What's built

- `app.py` — FastAPI backend (D1). Calls only `agent.loop.draft_patent`, so the doorway/HiddenLayer invariant holds.
- `static/index.html` — one self-contained page: intake (D2), draft studio with editable claims (D3), grant + loophole report (D4). No build step, no CDN, theme-aware.

## JSON contract (what a Next.js frontend would call)

- `GET /api/health` → `{mode, model, hl_enabled}`
- `GET /api/sample` → a `Disclosure` to prefill the form
- `POST /api/draft` → body is a `Disclosure` (see `airtight/shapes.py`); returns `{draft: Draft, report: LoopholeReport}`
  - `LoopholeReport` = `smart_catches` (self-critique) + `loopholes_closed` (memory pre-empted) + `security_findings` (Person 2's HiddenLayer catches) + `security_scanning` (false in stub/HL-off — honest, not faked)

## Still yours (D5-D6)

- D5 — the ablation chart view: consume `results/ablation/latest/results.json` (the harness already emits a standalone `chart.html` you can borrow from).
- D6 — the 3-moment demo runbook: glow-up (chart), trap (`python -m agent.ingest ... --fake-detect`), wall (`python -m containment.demo`).
