# attic/ — quarantined, not on the path

The `src/` ingestion pipeline from `01f4daf` (~3.1k lines), root `config.py`, the eight `scripts/` that drive them, and `test_extractor.py`. **Nothing here is imported by `airtight/`, `agent/`, `data/`, `surface/`, or `containment/`.** It is kept for its history and for the two rescue paths below — not as a base to build on.

## Why it's here

Every network path it speaks was retired and superseded by the one ODP host `data/pull_uspto.py` already uses (`api.uspto.gov/api/v1`):

| Dead endpoint | Where |
|---|---|
| `ped.uspto.gov/api/queries` (PEDS) | `config.py:28` |
| `api.patentsview.org/patents/query` (legacy PatentsView) | `config.py:36` |
| `ptabdata.uspto.gov/ptab-api` | `src/clients/ptab_client.py:37` |

It also speaks a `Disclosure` shape that predates the cross-lane contract — `src/fixture_builder.py:44` (`disclosure_id`/`cpc_class`/`problem_statement`) vs `airtight/shapes.py:11` (`id`/`technology_class`/`summary`/`details`). Porting the clients would have arrived where `data/pull_uspto.py` already is, so they were not repaired.

`src` was never a declared package (`pyproject.toml` lists only `airtight`, `agent`, `agent.eval`, `containment`, `surface`) — every consumer reached it through an explicit `sys.path.insert`, which is why moving it changed no install.

## Rescue paths

Two files are genuinely offline-clean — no dead clients, no network — and coupled to root `config.py` by exactly one attribute each:

- **`src/poison_builder.py`** (`:43`, needs `config.DATA_DIR`) — builds a two-vector poison PDF: white-on-white text plus XMP metadata, each independently detectable. Stronger than the current M6 fixture (`data/fixtures/poisoned_prior_art.txt`, plain text, one vector). `reportlab` is already installed. **To rescue:** replace `import config` with a local path constant, move to a live path. No other edit.
- **`src/fixture_builder.py`** (`:32`, same) — 5 hand-written synthetic disclosures. Superseded for benchmark use by the 38 real USPTO pairs the puller produces, which are real PTAB ground truth and already in-schema. Rescue only if synthetic fixtures are wanted for something else.

**Not rescuable cheaply:** `oa_extractor.py` needs four regex tables from `config.py` and is superseded by the rejection parsing in `data/pull_uspto.py`. `corpus_builder.py`, `pipeline.py`, and `groundtruth_builder.py` import the dead clients directly.

`test_extractor.py` (23 tests, with `sample_oa.txt`) moved with the code it covers. It passed, but it was covering a module nothing on the path calls.
