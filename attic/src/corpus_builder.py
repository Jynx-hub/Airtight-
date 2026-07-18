"""
src/corpus_builder.py  [E1]
============================
Builds the warming set: granted patents in JSON format.

Pulls from PatentsView (structured claim text) and cross-references PEDS
for OA history. Outputs one JSON file per patent under data/corpus/patents/.

Usage::

    python scripts/build_corpus.py --cpc G06F --warming 50 --extended 300
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config
from src.clients.patentsview_client import PatentsViewClient
from src.clients.peds_client import PEDSClient

logger = logging.getLogger(__name__)

# Directories
CORPUS_DIR = config.DATA_DIR / "corpus"
PATENTS_DIR = CORPUS_DIR / "patents"


class CorpusBuilder:
    """
    Fetches granted patents and writes them to data/corpus/patents/{patent_number}.json.

    Two tiers:
      - warming_set: the ~50 patents the robot is warmed on
      - extended_set: additional patents for bulk ingest tests
    """

    def __init__(
        self,
        cpc_classes: list[str] | None = None,
        warming_count: int = 50,
        extended_count: int = 300,
        output_dir: Path | None = None,
    ):
        self.cpc_classes = cpc_classes or ["G06F", "H04L"]
        self.warming_count = warming_count
        self.extended_count = extended_count
        self.output_dir = output_dir or PATENTS_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    async def build(self) -> dict:
        """
        Build the corpus. Returns manifest dict.
        """
        warming_ids: list[str] = []
        extended_ids: list[str] = []
        total = 0

        for cpc in self.cpc_classes:
            target = self.warming_count + self.extended_count
            per_class = target // len(self.cpc_classes)
            warming_per = self.warming_count // len(self.cpc_classes)

            logger.info("Fetching %d patents for CPC class %s...", per_class, cpc)
            fetched = await self._fetch_class(cpc, per_class)

            for i, patent in enumerate(fetched):
                pnum = patent.get("patent_number", "")
                if not pnum:
                    continue
                self._write_patent(patent)
                total += 1
                if i < warming_per:
                    warming_ids.append(pnum)
                else:
                    extended_ids.append(pnum)

        manifest = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "cpc_classes": self.cpc_classes,
            "total_patents": total,
            "warming_set_count": len(warming_ids),
            "extended_set_count": len(extended_ids),
            "warming_set_ids": warming_ids,
            "extended_set_ids": extended_ids,
        }

        manifest_path = CORPUS_DIR / "manifest.json"
        manifest_path.write_text(json.dumps(manifest, indent=2))
        logger.info("Corpus manifest written: %s (%d patents)", manifest_path, total)
        return manifest

    async def _fetch_class(self, cpc: str, limit: int) -> list[dict]:
        """Fetch up to `limit` granted patents for a CPC class prefix."""
        results = []
        pv_sem = asyncio.Semaphore(config.PATENTSVIEW_RATE_LIMIT)

        async with PatentsViewClient(semaphore=pv_sem) as pv:
            async for patent in pv.search_by_cpc(cpc, limit=limit):
                # Enrich with full claim text
                patent_id = patent.get("patent_id", "")
                if patent_id:
                    claims = await pv.fetch_claims(patent_id)
                    patent["claims"] = _normalize_claims(claims)
                else:
                    patent["claims"] = []

                patent["cpc_class"] = cpc
                patent["source"] = "patentsview"
                results.append(patent)

        return results

    def _write_patent(self, raw: dict) -> Path:
        """Normalize and write one patent to its JSON file."""
        normalized = {
            "app_number":           raw.get("app_number") or raw.get("applicationNumberText", ""),
            "patent_number":        raw.get("patent_number", ""),
            "cpc_class":            raw.get("cpc_class", ""),
            "title":                raw.get("patent_title") or raw.get("patentTitle", ""),
            "filing_date":          _normalize_date(raw.get("app_date") or raw.get("appFilingDate")),
            "grant_date":           _normalize_date(raw.get("patent_date")),
            "abstract":             raw.get("abstract", ""),
            "claims":               raw.get("claims", []),
            "description_excerpt":  raw.get("description_excerpt", ""),
            "source":               raw.get("source", "patentsview"),
        }

        pnum = normalized["patent_number"] or normalized["app_number"] or "unknown"
        safe_name = pnum.replace("/", "_").replace(",", "")
        out_path = self.output_dir / f"{safe_name}.json"
        out_path.write_text(json.dumps(normalized, indent=2, ensure_ascii=False))
        return out_path


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _normalize_claims(raw_claims: list[dict]) -> list[dict]:
    return [
        {
            "number":      c.get("claim_number") or c.get("claim_sequence", 0),
            "text":        c.get("claim_text", "").strip(),
            "independent": bool(c.get("independent", True)),
        }
        for c in raw_claims
        if c.get("claim_text")
    ]


def _normalize_date(val: Any) -> str | None:
    if not val:
        return None
    s = str(val)[:10]
    # Try to parse and reformat as YYYY-MM-DD
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%m/%d/%Y"):
        try:
            from datetime import datetime as dt
            return dt.strptime(s, fmt).strftime("%Y-%m-%d")
        except ValueError:
            continue
    return s or None
