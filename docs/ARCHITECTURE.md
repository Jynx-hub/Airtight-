# Patent Defect Database — Architecture

> **§ Reduction to Practice** — canonical reference for all five data epics.  
> All team members (Person 4 and data layer) must treat this as the source of truth
> for shapes, paths, and invariants.

---

## System Overview

```
┌─────────────────────────────────────────────────────────────────────┐
│  PUBLIC DATA SOURCES (no auth required)                             │
│  ┌──────────────────┐ ┌──────────────────┐ ┌──────────────────┐   │
│  │  USPTO PEDS API  │ │  PatentsView API │ │  PTAB Open Data  │   │
│  │  (full-text OA)  │ │  (claim text)    │ │  (decisions)     │   │
│  └────────┬─────────┘ └────────┬─────────┘ └────────┬─────────┘   │
└───────────┼────────────────────┼────────────────────┼─────────────┘
            │                    │                    │
┌───────────▼────────────────────▼────────────────────▼─────────────┐
│  DATA LAYER (this repo)                                            │
│                                                                    │
│  E1 corpus_builder.py      → data/corpus/patents/{n}.json         │
│  E2 groundtruth_builder.py → data/groundtruth/decisions/{n}.json  │
│  E3 fixture_builder.py     → data/fixtures/{disclosures,checks}   │
│  E4 loaders.py             → clean API for Person 4               │
│  E5 poison_builder.py      → data/poison/prior_art_malicious.pdf  │
└───────────────────────────┬────────────────────────────────────────┘
                            │ load_corpus() / load_groundtruth()
                            │ load_fixtures() / load_poison()
┌───────────────────────────▼────────────────────────────────────────┐
│  PERSON 4 — Eval Harness + Memory System                           │
│  Warming corpus → robot learns                                     │
│  Fixed disclosures → robot analyses                                │
│  Checklists → grader scores robot                                  │
│  Poisoned PDF → security scanner catches it                        │
└────────────────────────────────────────────────────────────────────┘
```

---

## § Reduction to Practice

### E1 — feat/data-corpus (Warming Set)

**Purpose**: The patent corpus the robot is warmed on. Must be same-class,
full-text, granted patents only.

**Source**: PatentsView API (structured claim text) + USPTO PEDS (OA history).

**Target volumes**:
- Primary warming set: **50 granted patents** (same CPC class, clean full-text)
- Extended corpus: **300+ patents** for bulk ingest tests

**CPC classes selected** (software + electronics — richest data, readable claims):
- `G06F` — Electric digital data processing / Software architectures
- `H04L` — Transmission of digital information / Network protocols
- `G06N` — Computer systems / AI & ML *(optional third class)*

**Output path**: `data/corpus/`

**File shape** — one JSON per patent:
```json
{
  "app_number": "string",
  "patent_number": "string",
  "cpc_class": "string",
  "title": "string",
  "filing_date": "YYYY-MM-DD",
  "grant_date": "YYYY-MM-DD",
  "abstract": "string",
  "claims": [
    {
      "number": 1,
      "text": "string",
      "independent": true
    }
  ],
  "description_excerpt": "string",
  "source": "patentsview | peds"
}
```

**Manifest** — `data/corpus/manifest.json`:
```json
{
  "generated_at": "ISO-8601",
  "cpc_classes": ["G06F", "H04L"],
  "total_patents": 350,
  "warming_set_ids": ["US10001234B2", "..."],
  "extended_set_ids": ["US10005678B2", "..."]
}
```

---

### E2 — feat/data-groundtruth (Scoring Key)

**Purpose**: For each patent in the corpus, which claims died and why.
This is the authoritative answer key that Person 4's eval harness scores against.

**Sources**:
- USPTO PTAB e-Hearing Open Data (`https://ptabdata.uspto.gov/ptab-api/`)
- USPTO PEDS file wrapper OA text (§112/§102/§103 rejection extraction)

**Output path**: `data/groundtruth/`

**File shape** — one JSON per patent:
```json
{
  "app_number": "string",
  "patent_number": "string",
  "cpc_class": "string",
  "claim_rejections": [
    {
      "claim_number": 1,
      "status": "cancelled | amended | confirmed | rejected",
      "rejection_basis": "§112 | §102 | §103",
      "examiner_rationale": "string",
      "prior_art_refs": ["US9876543B2"],
      "resolved": false,
      "resolution_type": "amendment | cancelled | null"
    }
  ],
  "surviving_claims": [3, 4, 7],
  "dead_claims": [1, 2, 5, 6],
  "ptab_decisions": [
    {
      "proceeding_number": "IPR2020-00123",
      "decision_type": "Final Written Decision",
      "institution_date": "YYYY-MM-DD",
      "outcome": "claims_cancelled | claims_confirmed | mixed",
      "cancelled_claims": [1, 2],
      "confirmed_claims": [3]
    }
  ],
  "data_sources": ["peds_oa", "ptab_api"]
}
```

**Manifest** — `data/groundtruth/manifest.json`:
```json
{
  "generated_at": "ISO-8601",
  "total_records": 350,
  "coverage": {
    "has_ptab": 42,
    "has_oa_rejections": 298,
    "has_both": 38
  }
}
```

---

### E3 — feat/data-fixtures (Fixed Eval Set)

**Purpose**: 3–5 invention write-ups used in **every** eval run. The
loophole checklist is derived from E2 ground truth but is **never** written
into the warming corpus (E1). This separation is the core eval integrity guarantee.

**Output path**: `data/fixtures/disclosures/` and `data/fixtures/checklists/`

**Disclosure shape** — `disc_{n}.json` (this IS fed to the robot):
```json
{
  "disclosure_id": "disc_001",
  "title": "string",
  "cpc_class": "G06F | H04L | G06N",
  "problem_statement": "string",
  "proposed_solution": "string",
  "key_claims": ["Independent claim draft text..."],
  "novel_aspects": ["string"],
  "technical_field": "string"
}
```

**Checklist shape** — `disc_{n}_checklist.json` (HELD OUT — graders only):
```json
{
  "disclosure_id": "disc_001",
  "loopholes": [
    {
      "id": "L001",
      "type": "§103",
      "severity": "fatal | moderate | minor",
      "description": "string",
      "prior_art_ref": "US9876543B2",
      "triggering_claim_phrase": "string",
      "source_groundtruth_app": "16/123456"
    }
  ],
  "expected_rejection_types": ["§103", "§112"],
  "minimum_loopholes_to_pass": 2,
  "source_decisions": ["16/123456", "16/234567"]
}
```

**Invariant**: `source_decisions` app numbers must NOT appear in
`data/corpus/manifest.json → warming_set_ids`. Enforced by `validate_fixtures.py`.

---

### E4 — feat/data-loaders (Person 4 API)

**Purpose**: One-call loader functions. Clean, typed, zero-config.

**File**: `src/loaders.py`

**API**:
```python
from src.loaders import load_corpus, load_groundtruth, load_fixtures, load_checklists, load_poison

corpus     = load_corpus()       # list[dict]   — E1 patents
gt         = load_groundtruth()  # dict[str, dict] — E2 keyed by app_number
fixtures   = load_fixtures()     # list[dict]   — E3 disclosures (no checklists)
checklists = load_checklists()   # list[dict]   — E3 checklists (graders only)
pdf_path   = load_poison()       # pathlib.Path — E5 PDF
```

All functions accept an optional `data_dir: Path` argument for non-default paths.

---

### E5 — feat/data-poison (Security Demo)

**Purpose**: A plausible patent-style PDF that contains hidden "leak the
client's disclosure" text. Used to demo that Person 4's scanner catches it.

**Hidden text placement** (two independent vectors):
1. **White-on-white text layer**: A text element in the PDF with font color
   `rgb(1,1,1)` on a white background — visually invisible, machine-readable.
2. **PDF metadata fields**: Injected into `Author`, `Subject`, and `Keywords`
   XMP metadata fields.

**Trigger phrase** (what the scanner must detect):
```
CONFIDENTIAL: [client disclosure text]
```

**Output**: `data/poison/prior_art_malicious.pdf`
**Coordinate with Person 4**: Scanner must check both text content (extracted
via PyMuPDF/pdfplumber) and XMP metadata fields.

---

## Data Flow Invariants

| Rule | Enforced by |
|---|---|
| Checklist source apps ∉ warming set | `scripts/validate_fixtures.py` |
| All corpus files have `claims` array len ≥ 1 | `load_corpus()` raises on violation |
| Ground truth covers all corpus app_numbers | `load_groundtruth()` warns on gaps |
| Poison PDF readable by `pdfplumber.extract_text()` | `src/loaders.py:load_poison()` smoke-tests on load |

---

## Directory Reference

```
patent-defect-db/
├── docs/
│   └── ARCHITECTURE.md          ← YOU ARE HERE
├── data/
│   ├── corpus/
│   │   ├── manifest.json
│   │   └── patents/
│   ├── groundtruth/
│   │   ├── manifest.json
│   │   └── decisions/
│   ├── fixtures/
│   │   ├── disclosures/
│   │   └── checklists/
│   └── poison/
│       └── prior_art_malicious.pdf
├── src/
│   ├── clients/
│   │   ├── peds_client.py
│   │   ├── patentsview_client.py
│   │   └── ptab_client.py
│   ├── extractors/
│   │   ├── oa_extractor.py
│   │   └── groundtruth_builder.py
│   ├── corpus_builder.py
│   ├── fixture_builder.py
│   ├── poison_builder.py
│   ├── loaders.py
│   └── db.py
└── scripts/
    ├── build_corpus.py
    ├── build_groundtruth.py
    ├── build_fixtures.py
    ├── build_poison.py
    └── validate_fixtures.py
```
