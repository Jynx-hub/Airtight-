# surface/ — the two frames

The Applicant Surface (what a user touches) and the Engine panel (what the judges
should see underneath). Tasks D1–D5: `docs/WORKSTREAMS.md`.

## Run it

```bash
pip install -e ".[web]"
uvicorn surface.app:app --reload      # http://localhost:8000
```

Works in stub mode with no network, no GPU and no keys — every panel reads
committed artifacts off disk. Set `AIRTIGHT_MODE=live` (+ the Modal URL) for real
drafts.

**No Node needed to run it.** `static/airtight-kit.js` is committed. You only need
esbuild if you edit the JSX:

```bash
bash surface/build.sh                 # ui/*.jsx → static/airtight-kit.js
```

React and the three font families are vendored under `static/`, so the surface
renders correctly with the network off. That is a hard requirement, not a
nicety — do not reintroduce a CDN `<script>` or a Google Fonts `@import`.

## The frames

**`/` — intake.** Disclosure in → matched context → live pipeline → grant.
Retrieval runs *as you type*: it is BM25 over the corpus with no model call, so
watching the matched failure modes shift while the invention is described costs
nothing. Drafting goes through `POST /api/draft/start` + polling, so the loop's
turns (plan → draft → critique → revise → re-critique) are visible while they
run rather than hidden behind a multi-minute spinner. Polling rather than
streaming is deliberate — with reasoning off the streaming path routes output to
`reasoning_content` and leaves `content` empty (upstream, `docs/THROUGHPUT.md`).

**`/admin` — engine.** Corpus facets by statute and CPC; a retrieval inspector
that shows which *higher-ranked* records diversification passed over; the
empty-vs-warmed ablation; the five-hop guardrail bus; the vLLM throughput curve;
and the four containment tiers.

## Files

| File | Role |
|---|---|
| `app.py` | Routing only. Calls just `agent.loop.draft_patent`, so the doorway / HiddenLayer invariant holds. |
| `sources.py` | Tolerant read-only views over `results/`, `data/`, `memory/`, `runtime/bench-results/`. Nothing raises; missing or stale data becomes a labelled seam. |
| `explain.py` | Recomputes *why* retrieval picked what it picked, reusing `agent/memory.py`'s own `_rank` / `diversify_by_statute` / BM25 constants. |
| `jobs.py` | In-process job registry + the worker that runs a draft with a live transcript, and hands it the episode sink so a finished run becomes memory. |
| `ui/` | JSX source for both frames — `Intake.jsx`, `Engine.jsx`, `App.jsx`, the seam renderer in `common.jsx`, and the vendored Pete design-system components in `ui/ds/`. Not served. |
| `build.sh` | Compiles `ui/` → `static/airtight-kit.js` with esbuild. Run it only after editing `ui/`. |
| `static/` | `airtight.css` (the token layer), `index.html` + `admin.html` (thin shells), the committed `airtight-kit.js`, plus vendored `vendor/` (React) and `fonts/`. No CDN, no network. |

**Do not** reach into `agent/memory.py` or `agent/loop.py` from here. Retrieval is
frozen at a recorded SHA for the GPU re-run, and the loop's system prompts are
hashed into every ablation fingerprint — a display concern is not a reason to
touch either. `explain.py` exists precisely so the panel can show the reasoning
without the engine having to expose it.

## Seams

Anything not yet real renders a badge naming the exact path or command that fills
it (`NOT POPULATED · memory/episodes/… · AIRTIGHT_EPISODES_ENABLED=1`). That is a
house rule, not decoration: this lane already shipped one control that looked
interactive and silently discarded input (D3's claim textareas). If it looks
done, it must be done — or say plainly that it isn't.

Episodic memory is no longer one of them: `jobs.py` and the synchronous
`POST /api/draft` both pass `sources.episode_sink()`, so with
`AIRTIGHT_EPISODES_ENABLED=true` a finished draft records itself and the panel
counts up. The write is still gated inside `draft_patent`, and the M4 harness
passes no sink at all, so nothing here can reach a judged ablation.

Its seam has **three** states, because collapsing any two misdirects the fix:
flag off (nothing will ever fill it), flag on but nothing drafted yet (the next
draft will), and `NOTHING LEARNED YET` — episodes recorded that distilled nothing
new. That last one is where a stub-mode demo actually sits, and it used to be
invisible: `lessons` counted the raw `distilled` list, which `compress_run` seeds
with the run's *retrieved* records, so two runs that learned nothing reported "10
lessons distilled."

**A lesson is what `compress_run` minted** — `source` starting `episode:` — not
everything the episode carried. Counting "records not already in the corpus"
instead looks right until a draft carrying live USPTO prior art lands, at which
point the panel credits the agent with learning 5 references it merely copied.

Both stores are gitignored, so a fresh clone starts empty — populate them with
`.venv/bin/python scripts/seed_memory.py --n 5`, which runs the real paths rather
than writing fixture records. Ingest seeds honestly offline (the clean fixture is
admitted, the poisoned one quarantined); lessons need `AIRTIGHT_MODE=live`.

Current seams: ingested records (empty), the ablation
run (superseded corpus, awaiting the GPU re-run), containment enforcement
(simulated — `print()`, not Landlock), `inference.local` (naming contract, no
gateway until F5), and claim editing (needs `PATCH /api/draft/{job_id}`).

## JSON contract

```
GET  /api/health                     → {mode, model, hl_enabled}
GET  /api/sample                     → a Disclosure to prefill intake
POST /api/draft                      → Disclosure → {draft, report}   (synchronous)
POST /api/draft/start                → Disclosure → {job_id}
GET  /api/draft/{job_id}             → {status, elapsed_s, retrieval, stages[], draft?, report?}
GET  /api/disclosures                → pulled disclosures, summary only
GET  /api/memory/stats               → corpus / episode / ingested counts + facets
GET  /api/memory/records             → ?statute= &cpc= &q= &limit=
POST /api/memory/retrieve            → Disclosure → the k picks, scored and explained
GET  /api/memory/retrieve/{disc_id}  → same, against a corpus disclosure
GET  /api/ablation                   → runs + selected + caveat
GET  /api/security                   → hop × action matrix, live vs synthetic, event tail
GET  /api/throughput                 → sweeps + curve + knee
GET  /api/containment                → four tiers + network rules + seams
```

`LoopholeReport` = `smart_catches` (self-critique) + `loopholes_closed` (what memory
put in front of the drafting turn) + `security_findings` + `security_scanning`
(false in stub / HL-off — honest, not faked).

Note `loopholes_closed` is what the draft was *primed with*, not a verified cure.
Closure is graded by `agent/eval/judge.py`, which does not run on this path — the
UI says so rather than implying a graded result.
