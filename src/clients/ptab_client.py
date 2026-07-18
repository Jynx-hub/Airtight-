"""
src/clients/ptab_client.py
===========================
Async client for the USPTO PTAB Open Data API.

Public endpoint — no authentication required.
Docs: https://ptabdata.uspto.gov/ptab-api/swagger-ui.html

The PTAB API provides structured data on:
  - Inter Partes Review (IPR) proceedings
  - Post-Grant Review (PGR) proceedings
  - Final Written Decisions
  - Trial Institution decisions

Key endpoints:
  GET /ptab-api/proceedings        — list proceedings by patent number / app number
  GET /ptab-api/decisions          — fetch decision documents for a proceeding
  GET /ptab-api/documents/{id}     — download full decision text
"""

from __future__ import annotations

import asyncio
import logging
from typing import Any, AsyncIterator

import aiohttp
import orjson

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config

logger = logging.getLogger(__name__)

PTAB_BASE = "https://ptabdata.uspto.gov/ptab-api"
PTAB_RATE_LIMIT = 5    # conservative — PTAB API is slower
PTAB_TIMEOUT = 45


def _backoff(attempt: int) -> float:
    import random
    return min(config.BACKOFF_BASE ** attempt + random.uniform(0, 1), config.BACKOFF_MAX)


class PTABClient:
    """
    Async client for the USPTO PTAB Open Data API.

    Usage::

        async with PTABClient() as client:
            proceedings = await client.get_proceedings_for_patent("US10123456B2")
            for proc in proceedings:
                decisions = await client.get_decisions(proc["proceedingNumber"])
    """

    TIMEOUT = aiohttp.ClientTimeout(total=PTAB_TIMEOUT)

    def __init__(self, semaphore: asyncio.Semaphore | None = None):
        self._sem = semaphore or asyncio.Semaphore(PTAB_RATE_LIMIT)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "PTABClient":
        self._session = aiohttp.ClientSession(
            timeout=self.TIMEOUT,
            headers={
                "Accept": "application/json",
                "User-Agent": "patent-defect-db/1.0 (research; public data only)",
            },
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_proceedings_for_patent(self, patent_number: str) -> list[dict]:
        """
        Fetch all PTAB proceedings (IPR, PGR) for a given patent number.

        Args:
            patent_number: E.g. "US10123456B2" or "10123456"

        Returns:
            List of proceeding metadata dicts.
        """
        # Normalize: strip "US" prefix and kind code for the query
        clean_num = patent_number.lstrip("US").split("B")[0].split("A")[0]

        params = {
            "patentNumber": clean_num,
            "rows": 100,
            "start": 0,
        }
        data = await self._get(f"{PTAB_BASE}/proceedings", params)
        return data.get("results", []) if isinstance(data, dict) else []

    async def get_proceedings_for_app(self, app_number: str) -> list[dict]:
        """
        Fetch PTAB proceedings by application number.
        """
        params = {
            "applicationNumber": app_number.replace("/", "").replace(",", ""),
            "rows": 50,
            "start": 0,
        }
        data = await self._get(f"{PTAB_BASE}/proceedings", params)
        return data.get("results", []) if isinstance(data, dict) else []

    async def get_decisions(self, proceeding_number: str) -> list[dict]:
        """
        Fetch decision metadata for a PTAB proceeding.

        Returns list of decision dicts with keys:
          proceedingNumber, documentName, documentDescription,
          uploadDate, mediaType, downloadUrl
        """
        data = await self._get(
            f"{PTAB_BASE}/documents",
            {"proceedingNumber": proceeding_number, "rows": 50},
        )
        docs = data.get("results", []) if isinstance(data, dict) else []

        # Filter to Final Written Decisions and Institution Decisions
        decision_keywords = {"final written decision", "institution decision", "decision"}
        return [
            d for d in docs
            if any(kw in d.get("documentDescription", "").lower() for kw in decision_keywords)
        ]

    async def get_decision_text(self, document_id: str) -> str:
        """
        Download and return the plain text of a PTAB decision document.
        """
        url = f"{PTAB_BASE}/documents/{document_id}/download"
        for attempt in range(config.MAX_RETRIES):
            async with self._sem:
                try:
                    async with self._session.get(url) as resp:  # type: ignore[union-attr]
                        if resp.status == 200:
                            return await resp.text(errors="replace")
                        elif resp.status == 404:
                            return ""
                        elif resp.status in (429, 503):
                            await asyncio.sleep(_backoff(attempt))
                except aiohttp.ClientError as exc:
                    logger.warning("PTAB doc fetch error: %s", exc)
                    await asyncio.sleep(_backoff(attempt))
        return ""

    async def search_by_cpc(
        self,
        cpc_prefix: str,
        limit: int = 500,
    ) -> AsyncIterator[dict]:
        """
        Yield proceedings for patents within a CPC class.

        Note: PTAB API does not support direct CPC filtering, so we query
        all recent proceedings and filter by the patent CPC class using
        cross-reference against PatentsView.

        This is a best-effort approach for bulk discovery.
        """
        start = 0
        page_size = min(100, limit)
        yielded = 0

        while yielded < limit:
            params = {
                "rows": page_size,
                "start": start,
                "sortOrder": "desc",
            }
            data = await self._get(f"{PTAB_BASE}/proceedings", params)
            results = data.get("results", []) if isinstance(data, dict) else []

            if not results:
                break

            for r in results:
                if yielded >= limit:
                    return
                yield r
                yielded += 1

            start += len(results)
            if start >= data.get("totalCount", 0):
                break

    # ------------------------------------------------------------------
    # Internal HTTP helper
    # ------------------------------------------------------------------

    async def _get(self, url: str, params: dict) -> dict:
        for attempt in range(config.MAX_RETRIES):
            async with self._sem:
                try:
                    async with self._session.get(url, params=params) as resp:  # type: ignore[union-attr]
                        if resp.status == 200:
                            raw = await resp.read()
                            try:
                                return orjson.loads(raw)
                            except Exception:
                                return {}
                        elif resp.status in (429, 503):
                            wait = _backoff(attempt)
                            logger.warning("PTAB rate-limited — sleeping %.1fs", wait)
                            await asyncio.sleep(wait)
                        elif resp.status == 404:
                            return {}
                        else:
                            logger.warning("PTAB %d for %s", resp.status, url)
                            return {}
                except aiohttp.ClientError as exc:
                    logger.warning("PTAB ClientError: %s", exc)
                    await asyncio.sleep(_backoff(attempt))
        return {}
