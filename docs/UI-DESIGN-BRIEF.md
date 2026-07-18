# UI Design Brief — Applicant Surface

*A ready-to-paste prompt for a Claude Code session rebuilding `surface/static/index.html`.
Written 2026-07-18 against the D1/D2/D4 starter and the D3/D5 gaps recorded in
`docs/WORKSTREAMS.md`.*

---

```
You're rebuilding the Applicant Surface for Airtight — a patent-drafting tool for
independent inventors and small teams filing their own software/electronics patents.
Read before writing any code:

- README.md and docs/ARCHITECTURE.md (§Summary, §Layer 1) — the product concept
- surface/README.md — what's built, the JSON contract, what's still missing (D3, D5)
- surface/app.py — the FastAPI backend (do not modify the routes or response shapes)
- surface/static/index.html — the current working starter; you're replacing this
- airtight/shapes.py — the exact data shapes (Disclosure, Draft, EvalResult)
- docs/WORKSTREAMS.md, "Person 3 · Surface" section — the honest audit of what's
  actually done vs. cosmetic (D3's edit boxes currently discard input silently —
  fix that dishonesty, don't just re-skin it)

## Product context

Airtight is positioned as a robot patent attorney, not a form generator. The user
is a solo inventor or founder who cannot afford a $15k attorney draft and needs to
trust that what comes out the other end is actually filing-ready — rigorous, not
templated. The domain is entirely software/electronics (CPC classes like G06F),
so the tool's whole value prop is closing the specific failure modes examiners
reject on: §101 abstract-idea rejections, §112 indefiniteness, antecedent-basis
gaps, prior-art anticipation. The UI's job is to make that rigor *visible* at
every step — not just claim it in copy.

## The JSON contract — do not change

- `GET /api/health` → `{mode, model, hl_enabled}`
- `GET /api/sample` → a `Disclosure` to prefill intake
- `POST /api/draft` — body is a `Disclosure`:
  `{id, title, inventors: string[], technology_class, summary, details}`
  → returns `{draft: Draft, report: LoopholeReport}`:
  - `Draft` = `{disclosure_id, claims: string[], specification, critique_notes: string[], loopholes_closed: string[]}`
  - `LoopholeReport` = `{smart_catches: string[], loopholes_closed: string[], security_findings: [{hop, action, source?, categories: string[]}], security_scanning: bool}`

If your design needs separate CSS/JS/font files rather than one inline HTML file,
add `app.mount("/static", StaticFiles(directory=STATIC), name="static")` to
`surface/app.py` — that mount doesn't exist yet. Otherwise keep the backend
untouched.

## Three screens to build (same flow as today, elevated)

1. **Intake** — title, CPC class, inventors, summary, details → "Draft patent"
2. **Draft studio** — numbered claims, genuinely editable this time (client-side
   state is enough; there's no PATCH route yet, so don't imply the edit is saved
   server-side — say what's true)
3. **Grant** — filing-ready specification + the loophole report (self-critique
   catches, loopholes pre-empted from memory, HiddenLayer security findings —
   this last one must stay honest: say scanning is off when `security_scanning`
   is false, don't fake a clean scan)

## Design direction — inspired by Harvey AI and Legora, adapted to this subject

Both of those products earn their premium feel by looking like a serious legal
instrument, not a startup dashboard — restrained motion, editorial type, real
negative space. Don't copy their palette; Airtight's own material is the patent
document itself, so pull the distinctiveness from *that*: numbered claims with
hanging indents, a specification with a real document header, examiner
marginalia, the physical fact that a granted patent carries an embossed seal.
Airtight's name is the thesis — "no air in it," nothing a competitor can slip
through — so sealed/watertight is the throughline, not just a headline word.

**Color** (4–6 named hex, theme-aware — swap ink/vellum by
`prefers-color-scheme`, keep both fully styled):
- `--ink` `#12120E` — near-black warm graphite, dark-mode canvas
- `--vellum` `#F6F1E7` — warm parchment white, light-mode canvas + content cards
- `--seal` `#B08A46` — brass/gold, the grant-moment accent only — spend it once
- `--grant-green` `#1F5C3F` — deep forest, existing brand accent (index.html
  already uses `#2a6f4f`/`#4fae7d` — keep continuity), the "closed/pre-empted/
  granted" hue
- `--redline` `#9B3B2B` — muted brick/oxblood for defects and flagged findings —
  reads as an examiner's red pen, not an SaaS error-red
- `--ink-2` `#6B6A61` — secondary ink for labels, captions, metadata

**Type** — three roles, used with restraint:
- Display serif for the wordmark, section heads, and specification/claims
  headers — a high-contrast transitional serif (Fraunces-class), evokes gazette
  typesetting. Self-host 2–3 weights under `surface/static/fonts/` (no CDN call
  at runtime — matches the project's existing zero-dependency convention) or
  fall back cleanly to `ui-serif, Georgia, "Iowan Old Style", serif` if you'd
  rather stay single-file.
- Neutral grotesk (Inter-class) for every form control, button, and body line —
  the quiet workhorse that makes the serif read as a deliberate choice, not the
  whole voice.
- Monospace (IBM Plex Mono-class) for claim numbers, CPC codes, and the docket
  ID — reinforces the engineering half of "software & electronics patents."

**Layout — a docket, not a wizard.** Replace any generic 1/2/3 stepper with the
real vocabulary a patent actually moves through: **FILED → UNDER REVIEW →
GRANTED**. This isn't decorative numbering — it's the actual USPTO prosecution
states, so use them as a persistent left rail (collapses under the content on
mobile) showing which stage the current disclosure is in, plus its docket ID.
Content lives in a vellum "docket sheet" card to the right. In the draft studio,
render claims as real numbered patent claims (hanging indent, claim number in
brass mono) with critique notes as marginalia in a right-hand gutter rather than
a separate list underneath — same visual language carries into the grant
screen's loophole report so it reads as one continuous document, not bolted-on
panels.

**Signature moment.** When a draft completes, a brass seal/stamp animates onto
the specification header — a single restrained impression (scale + shadow
settle, no bounce, respects `prefers-reduced-motion`) that reads "GRANTED."
Use this exactly once. Don't scatter seal/stamp motifs elsewhere — the whole
point is that it's earned at the one moment a real patent actually gets one.

## Constraints (non-negotiable)

- Fully responsive down to mobile; visible keyboard focus on every interactive
  element; respect `prefers-reduced-motion`
- Theme-aware in both directions (light and dark), not just one with a dark
  mode afterthought
- No dead-end interactions — if something looks editable or clickable, it must
  do something real, or say plainly that it doesn't yet (this project has
  already shipped one dishonest control; don't repeat it)
- Copy is written from the inventor's side of the screen: plain verbs, no
  filler, no "submit" where "Draft patent" is what's actually happening;
  errors state what went wrong and what to do, in the tool's voice

Build against `GET /api/sample` for realistic content during development (a
real fixture: "Predictive cache eviction using access-pattern embeddings",
CPC G06F) rather than lorem ipsum.
```

---

## Notes on scope

- The palette/type/layout are anchored in the patent-document artifact itself
  (claims, specifications, examiner marginalia, the grant seal) rather than
  Harvey's or Legora's actual colors — copying their palette would read as
  derivative next to them, not premium.
- Scoped to the three working screens (D1/D2/D4-equivalent). D5 (ablation
  chart) and D6 (demo runbook) are out of scope here — both are downstream of
  real patent/PTAB data that doesn't exist yet (`docs/WORKSTREAMS.md`, Person 1
  status). Write a follow-up brief once that data lands.
- Flags the missing `StaticFiles` mount in `surface/app.py`, needed if the
  rebuild wants separate font/CSS/JS assets instead of one inline file.
