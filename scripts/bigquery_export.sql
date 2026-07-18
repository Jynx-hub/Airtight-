-- BigQuery export: pull raw OA-containing patent records from
-- Google Patents Public Data (patents-public-data project).
--
-- Prerequisites:
--   gcloud auth application-default login
--   bq query --use_legacy_sql=false --format=json < scripts/bigquery_export.sql \
--       > data/bq_raw.jsonl
--
-- Free tier: 1 TB/month query limit. This query scans ~50-80 GB.
-- Estimated cost at paid tier: ~$0.40 per run.
--
-- Output columns map directly to the pipeline's ingestion record schema.

SELECT
    pubs.publication_number,
    pubs.application_number,
    pubs.filing_date,
    pubs.title.text                          AS title,
    pubs.abstract.text                       AS abstract_text,

    -- First-listed CPC code prefix
    (SELECT c.code
     FROM UNNEST(pubs.cpc) AS c
     WHERE REGEXP_CONTAINS(c.code, r'^(G06F|H04L|H01L|G06N)')
     LIMIT 1)                                AS cpc_class,

    -- Concatenated independent claim text
    (SELECT STRING_AGG(cl.text, ' || ')
     FROM UNNEST(pubs.claims_localized) AS cl
     WHERE cl.language = 'en')              AS claims_text,

    -- Description sections (first 3000 chars for OA text proxy)
    SUBSTR(
      (SELECT STRING_AGG(d.text, ' ')
       FROM UNNEST(pubs.description_localized) AS d
       WHERE d.language = 'en'),
      1, 3000
    )                                        AS description_excerpt

FROM `patents-public-data.patents.publications` AS pubs,
     UNNEST(pubs.cpc) AS cpc_entry

WHERE
    -- Target CPC classes
    REGEXP_CONTAINS(cpc_entry.code, r'^(G06F|H04L|H01L|G06N)')

    -- US applications only
    AND STARTS_WITH(pubs.country_code, 'US')

    -- Filed 2000 onwards for relevance
    AND pubs.filing_date >= 20000101

    -- Must have claim text
    AND ARRAY_LENGTH(pubs.claims_localized) > 0

    -- Deduplicate: one row per application
GROUP BY
    pubs.publication_number,
    pubs.application_number,
    pubs.filing_date,
    pubs.title.text,
    pubs.abstract.text,
    claims_text,
    description_excerpt,
    cpc_class

HAVING cpc_class IS NOT NULL

ORDER BY pubs.filing_date DESC
LIMIT 200000;
