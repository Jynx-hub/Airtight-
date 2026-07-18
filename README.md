# Patent Prosecution Defect Database

A local Python pipeline that queries **public** USPTO patent datasets, extracts statutory rejection records (§112, §102, §103) from Office Action text, and stores them in a structured DuckDB database.

**Target:** 50,000+ records across CPC classes G06F, H04L, H01L, G06N.  
**Authentication:** None — all data sources are fully public.

---

## Data Sources

| Source | Endpoint | Auth |
|---|---|---|
| USPTO PEDS | `https://ped.uspto.gov/api/queries` | None |
| PatentsView | `https://api.patentsview.org/patents/query` | None |
| Google Patents (BigQuery) | `patents-public-data.patents.publications` | GCP account (optional) |

---

## Quick Start

```bash
# 1. Install dependencies
pip install -r requirements.txt

# 2. Run a small smoke test (100 records, no writes)
python scripts/run_ingestion.py --cpc G06F --limit 100 --dry-run

# 3. Full ingestion for all CPC classes (writes to DuckDB)
python scripts/run_ingestion.py --cpc G06F H04L H01L G06N --limit 15000 --workers 8

# 4. Query the results
duckdb data/patent_defects.duckdb \
  "SELECT statutory_defect_category, COUNT(*) as n \
   FROM patent_defects GROUP BY 1 ORDER BY 2 DESC"
```

---

## Output Schema

Each extracted record is stored as:

```json
{
  "app_number": "string",
  "cpc_class": "string",
  "filing_date": "date",
  "vulnerable_claim_shape": "string",
  "statutory_defect_category": "string (§112 | §102 | §103)",
  "examiner_rationale": "string",
  "remediated_claim_shape": "string",
  "raw_oa_text": "string",
  "source": "string (peds | patentsview | bigquery)",
  "ingested_at": "timestamp"
}
```

---

## CLI Reference

```
python scripts/run_ingestion.py [OPTIONS]

Options:
  --cpc       CPC class prefix(es) to target (default: G06F H04L H01L G06N)
  --limit     Max records per CPC class (default: 15000)
  --workers   Concurrent API workers (default: 8, max: 20)
  --dry-run   Fetch and extract but do not write to DB
  --resume    Resume from checkpoint file (skips already-ingested app numbers)
  --source    Data source: peds | patentsview | both (default: both)
  --db        Path to DuckDB file (default: data/patent_defects.duckdb)
  --verbose   Print extraction details per record
```

---

## BigQuery (Optional — Bulk Mode)

For faster ingestion of the full corpus, export from BigQuery first:

```bash
# Requires: gcloud auth application-default login
bq query --use_legacy_sql=false < scripts/bigquery_export.sql > data/bq_raw.jsonl

# Then ingest from the local export
python scripts/run_ingestion.py --source local --input data/bq_raw.jsonl
```

See [`scripts/bigquery_export.sql`](scripts/bigquery_export.sql) for the query.

---

## Project Structure

```
patent-defect-db/
├── config.py                  # CPC targets, API URLs, rate limits
├── requirements.txt
├── db/
│   └── schema.sql             # DuckDB DDL
├── src/
│   ├── clients/
│   │   ├── peds_client.py     # USPTO PEDS async client
│   │   └── patentsview_client.py
│   ├── extractors/
│   │   └── oa_extractor.py    # Regex+rule OA text parser
│   ├── pipeline.py            # Orchestrator
│   └── db.py                  # DuckDB helpers
├── scripts/
│   ├── run_ingestion.py       # CLI entry point
│   └── bigquery_export.sql    # Optional BQ export query
├── data/                      # .gitignored — output goes here
└── tests/
    ├── test_extractor.py
    └── fixtures/sample_oa.txt
```
