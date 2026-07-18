-- DuckDB schema for the patent prosecution defect database
-- Run automatically by src/db.py on first connection.

CREATE TABLE IF NOT EXISTS patent_defects (
    id                       VARCHAR   PRIMARY KEY,   -- SHA-1(app_number + defect_category + claim_hash)
    app_number               VARCHAR   NOT NULL,
    cpc_class                VARCHAR   NOT NULL,      -- G06F | H04L | H01L | G06N
    filing_date              DATE,
    publication_number       VARCHAR,
    title                    VARCHAR,

    -- Core extraction fields (matches output schema)
    vulnerable_claim_shape   TEXT      NOT NULL,
    statutory_defect_category VARCHAR  NOT NULL,      -- §112 | §102 | §103
    examiner_rationale       TEXT      NOT NULL,
    remediated_claim_shape   TEXT,                    -- NULL if no successful amendment found

    -- Provenance
    raw_oa_text              TEXT,
    oa_date                  DATE,
    source                   VARCHAR   NOT NULL,      -- peds | patentsview | bigquery | local
    ingested_at              TIMESTAMP NOT NULL DEFAULT current_timestamp,

    -- Quality flags
    has_amendment            BOOLEAN   DEFAULT FALSE,
    extraction_confidence    FLOAT     DEFAULT 1.0    -- 1.0 = rule-matched; lower = heuristic
);

-- Indexes for common analytical queries
CREATE INDEX IF NOT EXISTS idx_cpc          ON patent_defects (cpc_class);
CREATE INDEX IF NOT EXISTS idx_defect       ON patent_defects (statutory_defect_category);
CREATE INDEX IF NOT EXISTS idx_filing_date  ON patent_defects (filing_date);
CREATE INDEX IF NOT EXISTS idx_app_number   ON patent_defects (app_number);

-- Summary view
CREATE VIEW IF NOT EXISTS defect_summary AS
SELECT
    cpc_class,
    statutory_defect_category,
    COUNT(*)                           AS record_count,
    COUNT(*) FILTER (WHERE has_amendment) AS with_amendment,
    MIN(filing_date)                   AS earliest_filing,
    MAX(filing_date)                   AS latest_filing,
    AVG(extraction_confidence)         AS avg_confidence
FROM patent_defects
GROUP BY cpc_class, statutory_defect_category
ORDER BY cpc_class, statutory_defect_category;
