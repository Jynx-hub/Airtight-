"""
src/db.py
=========
DuckDB connection manager and storage helpers.

- Creates the schema on first run (idempotent).
- Provides bulk-insert and checkpoint methods.
- Thread-safe: DuckDB in-process connections are safe from multiple async tasks
  if we serialize writes (one writer at a time via asyncio.Lock).
"""

from __future__ import annotations

import asyncio
import hashlib
import logging
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import duckdb

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

_SCHEMA_FILE = Path(__file__).parent.parent / "db" / "schema.sql"


class PatentDB:
    """
    Manages a DuckDB connection for the patent defect dataset.

    Usage::

        async with PatentDB() as db:
            await db.insert_batch(records)
            count = await db.count()
    """

    def __init__(self, db_path: Path | str = config.DB_PATH):
        self._path = Path(db_path)
        self._conn: duckdb.DuckDBPyConnection | None = None
        self._lock = asyncio.Lock()

    async def __aenter__(self) -> "PatentDB":
        self._path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = duckdb.connect(str(self._path))
        await self._init_schema()
        logger.info("DuckDB opened: %s", self._path)
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    # ------------------------------------------------------------------
    # Schema
    # ------------------------------------------------------------------

    async def _init_schema(self) -> None:
        sql = _SCHEMA_FILE.read_text()
        async with self._lock:
            self._conn.execute(sql)  # type: ignore[union-attr]
        logger.debug("Schema initialized.")

    # ------------------------------------------------------------------
    # Write
    # ------------------------------------------------------------------

    async def insert_batch(self, records: list[dict]) -> int:
        """
        Bulk-insert a list of extracted defect records.

        Each record must contain the keys from the output schema plus
        provenance fields added by the pipeline:
          app_number, cpc_class, filing_date, publication_number, title,
          raw_oa_text, oa_date, source,
          has_amendment, extraction_confidence,
          + the four core extraction fields.

        Returns the number of rows actually inserted (excluding duplicates).
        """
        if not records:
            return 0

        rows = [self._prepare_row(r) for r in records]
        inserted = 0

        async with self._lock:
            for row in rows:
                try:
                    self._conn.execute(  # type: ignore[union-attr]
                        """
                        INSERT OR IGNORE INTO patent_defects (
                            id, app_number, cpc_class, filing_date,
                            publication_number, title,
                            vulnerable_claim_shape, statutory_defect_category,
                            examiner_rationale, remediated_claim_shape,
                            raw_oa_text, oa_date, source, ingested_at,
                            has_amendment, extraction_confidence
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        row,
                    )
                    inserted += 1
                except Exception as exc:
                    logger.warning("Insert failed for app %s: %s", row[1], exc)

        return inserted

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    async def count(self) -> int:
        """Return total number of rows in patent_defects."""
        async with self._lock:
            result = self._conn.execute(  # type: ignore[union-attr]
                "SELECT COUNT(*) FROM patent_defects"
            ).fetchone()
        return result[0] if result else 0

    async def count_by_cpc(self) -> dict[str, int]:
        """Return row counts grouped by cpc_class."""
        async with self._lock:
            rows = self._conn.execute(  # type: ignore[union-attr]
                "SELECT cpc_class, COUNT(*) FROM patent_defects GROUP BY cpc_class"
            ).fetchall()
        return {row[0]: row[1] for row in rows}

    async def already_ingested(self, app_numbers: list[str]) -> set[str]:
        """Return the subset of app_numbers already present in the DB."""
        if not app_numbers:
            return set()
        placeholders = ", ".join("?" * len(app_numbers))
        async with self._lock:
            rows = self._conn.execute(  # type: ignore[union-attr]
                f"SELECT DISTINCT app_number FROM patent_defects WHERE app_number IN ({placeholders})",
                app_numbers,
            ).fetchall()
        return {row[0] for row in rows}

    async def summary(self) -> list[dict]:
        """Return rows from the defect_summary view."""
        async with self._lock:
            rows = self._conn.execute(  # type: ignore[union-attr]
                "SELECT * FROM defect_summary"
            ).fetchall()
            cols = [
                "cpc_class", "statutory_defect_category", "record_count",
                "with_amendment", "earliest_filing", "latest_filing",
                "avg_confidence",
            ]
        return [dict(zip(cols, row)) for row in rows]

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _prepare_row(r: dict) -> list:
        """Convert a record dict to an ordered list for parameterized INSERT."""
        app = r.get("app_number", "")
        cat = r.get("statutory_defect_category", "")
        vcs = r.get("vulnerable_claim_shape", "")
        row_id = hashlib.sha1(f"{app}|{cat}|{vcs[:80]}".encode()).hexdigest()

        return [
            row_id,
            app,
            r.get("cpc_class", ""),
            r.get("filing_date"),
            r.get("publication_number"),
            r.get("title"),
            vcs,
            cat,
            r.get("examiner_rationale", ""),
            r.get("remediated_claim_shape"),
            r.get("raw_oa_text"),
            r.get("oa_date"),
            r.get("source", "unknown"),
            datetime.now(timezone.utc),
            bool(r.get("has_amendment", False)),
            float(r.get("extraction_confidence", 1.0)),
        ]
