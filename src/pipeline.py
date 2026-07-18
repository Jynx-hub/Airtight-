"""
src/pipeline.py
===============
Async orchestrator: fetch → extract → store.

Flow per CPC class:
  1. Search PEDS for application numbers.
  2. For each application, fetch its Office Action document list.
  3. Download raw text for each OA document.
  4. Run OAExtractor over the text.
  5. Assemble full records (with provenance) and bulk-insert into DuckDB.

Checkpoint support:
  - After each batch of BATCH_COMMIT_SIZE records, saves a checkpoint JSON
    so ingestion can resume after interruption (--resume flag).
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path
from typing import Optional

from tqdm.asyncio import tqdm as atqdm
import tqdm as _tqdm

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from src.clients.peds_client import PEDSClient
from src.clients.patentsview_client import PatentsViewClient
from src.extractors.oa_extractor import OAExtractor
from src.db import PatentDB

logger = logging.getLogger(__name__)

BATCH_COMMIT_SIZE = 200   # insert into DB every N records


# ---------------------------------------------------------------------------
# Pipeline configuration
# ---------------------------------------------------------------------------

@dataclass
class PipelineConfig:
    cpc_classes: list[str] = field(default_factory=lambda: config.CPC_CLASSES)
    limit_per_class: int = config.DEFAULT_LIMIT_PER_CLASS
    workers: int = 8
    dry_run: bool = False
    resume: bool = False
    source: str = "both"       # "peds" | "patentsview" | "both"
    db_path: Path = config.DB_PATH
    verbose: bool = False


# ---------------------------------------------------------------------------
# Progress state
# ---------------------------------------------------------------------------

@dataclass
class IngestionStats:
    fetched: int = 0
    extracted: int = 0
    inserted: int = 0
    skipped: int = 0
    errors: int = 0
    start_time: float = field(default_factory=time.monotonic)

    def elapsed(self) -> str:
        secs = time.monotonic() - self.start_time
        m, s = divmod(int(secs), 60)
        h, m = divmod(m, 60)
        return f"{h:02d}:{m:02d}:{s:02d}"

    def report(self) -> str:
        return (
            f"fetched={self.fetched}  extracted={self.extracted}  "
            f"inserted={self.inserted}  skipped={self.skipped}  "
            f"errors={self.errors}  elapsed={self.elapsed()}"
        )


# ---------------------------------------------------------------------------
# Checkpoint helpers
# ---------------------------------------------------------------------------

def _load_checkpoint() -> set[str]:
    """Load already-ingested application numbers from checkpoint file."""
    path = config.CHECKPOINT_FILE
    if path.exists():
        try:
            data = json.loads(path.read_text())
            return set(data.get("ingested_app_numbers", []))
        except Exception:
            pass
    return set()


def _save_checkpoint(ingested: set[str]) -> None:
    config.CHECKPOINT_FILE.write_text(
        json.dumps({"ingested_app_numbers": sorted(ingested), "updated_at": datetime.utcnow().isoformat()})
    )


# ---------------------------------------------------------------------------
# Main pipeline
# ---------------------------------------------------------------------------

class IngestionPipeline:
    """
    Async ingestion pipeline.

    Usage::

        cfg = PipelineConfig(cpc_classes=["G06F"], limit_per_class=1000)
        async with IngestionPipeline(cfg) as pipeline:
            stats = await pipeline.run()
            print(stats.report())
    """

    def __init__(self, cfg: PipelineConfig):
        self.cfg = cfg
        self._stats = IngestionStats()
        self._extractor = OAExtractor()
        self._db: Optional[PatentDB] = None
        self._ingested_apps: set[str] = set()

        # Shared semaphores (shared across all concurrent workers)
        self._peds_sem = asyncio.Semaphore(min(cfg.workers, config.PEDS_RATE_LIMIT))
        self._pv_sem = asyncio.Semaphore(min(cfg.workers, config.PATENTSVIEW_RATE_LIMIT))

        # Pending records buffer
        self._buffer: list[dict] = []
        self._buffer_lock = asyncio.Lock()

    async def __aenter__(self) -> "IngestionPipeline":
        if not self.cfg.dry_run:
            self._db = PatentDB(self.cfg.db_path)
            await self._db.__aenter__()
        if self.cfg.resume:
            self._ingested_apps = _load_checkpoint()
            logger.info("Checkpoint loaded: %d apps already ingested.", len(self._ingested_apps))
        return self

    async def __aexit__(self, *args) -> None:
        if self._db:
            await self._db.__aexit__(*args)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    async def run(self) -> IngestionStats:
        """Run ingestion for all configured CPC classes and return stats."""
        logger.info("Starting ingestion: %s", self.cfg)

        for cpc in self.cfg.cpc_classes:
            logger.info("=== Processing CPC class: %s ===", cpc)
            await self._process_cpc_class(cpc)

        # Flush remaining buffer
        await self._flush_buffer(force=True)

        # Final checkpoint
        if not self.cfg.dry_run:
            _save_checkpoint(self._ingested_apps)

        logger.info("Ingestion complete. %s", self._stats.report())
        return self._stats

    # ------------------------------------------------------------------
    # Per-class processing
    # ------------------------------------------------------------------

    async def _process_cpc_class(self, cpc: str) -> None:
        """Enumerate applications for a CPC class and process them concurrently."""
        work_queue: asyncio.Queue[dict] = asyncio.Queue(maxsize=500)
        producer_done = asyncio.Event()

        # Launch producer + consumers concurrently
        await asyncio.gather(
            self._produce_apps(cpc, work_queue, producer_done),
            *[self._consume_apps(work_queue, producer_done, cpc) for _ in range(self.cfg.workers)],
        )

    async def _produce_apps(
        self,
        cpc: str,
        queue: asyncio.Queue,
        done: asyncio.Event,
    ) -> None:
        """Fetch application metadata and push onto the work queue."""
        try:
            async with PEDSClient(semaphore=self._peds_sem) as peds:
                count = 0
                async for app_meta in peds.search_by_cpc(cpc, limit=self.cfg.limit_per_class):
                    app_number = app_meta.get("applicationNumberText", "")
                    if not app_number:
                        continue
                    if self.cfg.resume and app_number in self._ingested_apps:
                        self._stats.skipped += 1
                        continue
                    await queue.put({"meta": app_meta, "cpc": cpc})
                    count += 1
                    self._stats.fetched += 1
        except Exception as exc:
            logger.error("Producer error for CPC %s: %s", cpc, exc)
        finally:
            done.set()

    async def _consume_apps(
        self,
        queue: asyncio.Queue,
        producer_done: asyncio.Event,
        cpc: str,
    ) -> None:
        """Process items from the work queue until queue is drained."""
        async with PEDSClient(semaphore=self._peds_sem) as peds:
            while True:
                try:
                    item = queue.get_nowait()
                except asyncio.QueueEmpty:
                    if producer_done.is_set():
                        break
                    await asyncio.sleep(0.05)
                    continue

                try:
                    await self._process_application(item["meta"], item["cpc"], peds)
                except Exception as exc:
                    logger.warning("Error processing app: %s", exc)
                    self._stats.errors += 1
                finally:
                    queue.task_done()

    # ------------------------------------------------------------------
    # Single application processing
    # ------------------------------------------------------------------

    async def _process_application(
        self, app_meta: dict, cpc: str, peds: PEDSClient
    ) -> None:
        """Fetch OA text for one application, extract defects, buffer for insert."""
        app_number = app_meta.get("applicationNumberText", "")
        if not app_number:
            return

        # Fetch Office Action document list
        oa_docs = await peds.fetch_office_actions(app_number)
        if not oa_docs:
            return

        for doc in oa_docs:
            doc_id = doc.get("documentIdentifier") or doc.get("documentCode", "")
            if not doc_id:
                continue

            # Download text
            oa_text = await peds.fetch_document_text(app_number, doc_id)
            if not oa_text:
                continue

            # Run extractor
            defects = self._extractor.extract(oa_text)
            if not defects:
                continue

            self._stats.extracted += len(defects)

            # Build full records with provenance
            filing_date = _parse_date(app_meta.get("appFilingDate"))
            oa_date = _parse_date(doc.get("mailDate"))

            for defect in defects:
                record = {
                    "app_number":               app_number,
                    "cpc_class":                cpc,
                    "filing_date":              filing_date,
                    "publication_number":       app_meta.get("appEarliestPublicationNumber"),
                    "title":                    app_meta.get("patentTitle"),
                    "vulnerable_claim_shape":   defect.vulnerable_claim_shape,
                    "statutory_defect_category": defect.statutory_defect_category,
                    "examiner_rationale":       defect.examiner_rationale,
                    "remediated_claim_shape":   defect.remediated_claim_shape,
                    "raw_oa_text":              oa_text[:5000],   # truncate for storage
                    "oa_date":                  oa_date,
                    "source":                   "peds",
                    "has_amendment":            defect.remediated_claim_shape is not None,
                    "extraction_confidence":    defect.extraction_confidence,
                }
                async with self._buffer_lock:
                    self._buffer.append(record)

            self._ingested_apps.add(app_number)

            if self.cfg.verbose:
                logger.info(
                    "  %s: %d defects extracted", app_number, len(defects)
                )

        # Periodic flush
        await self._flush_buffer()

    # ------------------------------------------------------------------
    # Buffer management
    # ------------------------------------------------------------------

    async def _flush_buffer(self, force: bool = False) -> None:
        """Insert buffered records into DuckDB when buffer reaches threshold."""
        async with self._buffer_lock:
            if not self._buffer:
                return
            if not force and len(self._buffer) < BATCH_COMMIT_SIZE:
                return

            batch = self._buffer[:]
            self._buffer.clear()

        if self.cfg.dry_run:
            logger.info("[dry-run] Would insert %d records.", len(batch))
            self._stats.inserted += len(batch)
            return

        if self._db:
            n = await self._db.insert_batch(batch)
            self._stats.inserted += n
            logger.info("Inserted %d records (total: %d)", n, self._stats.inserted)

            # Save checkpoint periodically
            _save_checkpoint(self._ingested_apps)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _parse_date(value: str | None) -> date | None:
    if not value:
        return None
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y", "%d-%b-%Y"):
        try:
            return datetime.strptime(value[:10], fmt).date()
        except ValueError:
            continue
    return None
