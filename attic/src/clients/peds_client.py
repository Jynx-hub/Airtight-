"""
src/clients/peds_client.py
==========================
Async client for the USPTO Patent Examination Data System (PEDS) API.

Public endpoint — no authentication required.
Docs: https://developer.uspto.gov/api-catalog/peds

The PEDS API exposes file wrapper (prosecution history) metadata and
document download links for all pending and issued US patent applications.

Key endpoints used:
  POST /api/queries          — search applications by CPC, status, date range
  GET  /api/file-wrappers/   — fetch individual file wrapper documents
"""

from __future__ import annotations

import asyncio
import json
import logging
import time
from typing import Any, AsyncIterator

import aiohttp

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _backoff(attempt: int) -> float:
    """Exponential backoff with jitter, capped at BACKOFF_MAX."""
    import random
    wait = min(config.BACKOFF_BASE ** attempt + random.uniform(0, 1), config.BACKOFF_MAX)
    return wait


async def _safe_json(response: aiohttp.ClientResponse) -> dict:
    """Parse JSON from a response; return empty dict on failure."""
    try:
        return await response.json(content_type=None)
    except Exception:
        text = await response.text()
        logger.debug("Non-JSON response body: %s", text[:200])
        return {}


# ---------------------------------------------------------------------------
# PEDSClient
# ---------------------------------------------------------------------------

class PEDSClient:
    """
    Async client for the USPTO PEDS API.

    Usage::

        async with PEDSClient() as client:
            async for app in client.search_by_cpc("G06F", limit=1000):
                print(app["applicationNumberText"])
    """

    BASE_URL = config.PEDS_BASE_URL
    TIMEOUT = aiohttp.ClientTimeout(total=config.PEDS_TIMEOUT)

    def __init__(self, semaphore: asyncio.Semaphore | None = None):
        self._sem = semaphore or asyncio.Semaphore(config.PEDS_RATE_LIMIT)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "PEDSClient":
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json",
            "User-Agent": "patent-defect-db/1.0 (research; public data only)",
        }
        self._session = aiohttp.ClientSession(
            headers=headers,
            timeout=self.TIMEOUT,
        )
        return self

    async def __aexit__(self, *_: Any) -> None:
        if self._session:
            await self._session.close()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def search_by_cpc(
        self,
        cpc_class: str,
        limit: int = 1000,
        start_date: str = "2000-01-01",
        end_date: str = "2024-12-31",
    ) -> AsyncIterator[dict]:
        """
        Yield application metadata records for a given CPC class prefix.

        PEDS query language uses Solr syntax. We search for:
          - CPC subgroup matching the class prefix
          - Applications with at least one Office Action (status filters)
        """
        page_size = min(config.PEDS_PAGE_SIZE, limit)
        offset = 0
        yielded = 0

        # Statutory rejection keywords that suggest relevant file wrappers
        status_filter = (
            "(appStatus_txt:*abandoned* OR appStatus_txt:*patented* "
            "OR appStatus_txt:*pending*)"
        )

        query = (
            f"(cpcCurrentInventiveIndexCpcGroupCode_txt:{cpc_class}*) "
            f"AND {status_filter} "
            f"AND appFilingDate:[{start_date}T00:00:00Z TO {end_date}T23:59:59Z]"
        )

        while yielded < limit:
            fetch_size = min(page_size, limit - yielded)
            payload = {
                "query": query,
                "filters": "",
                "fields": (
                    "applicationNumberText,patentTitle,appFilingDate,"
                    "appStatus_txt,publicationNumber,"
                    "cpcCurrentInventiveIndexCpcGroupCode_txt,"
                    "appEarliestPublicationNumber"
                ),
                "facets": "",
                "sort": [{"field": "appFilingDate", "order": "desc"}],
                "start": offset,
                "rows": fetch_size,
                "searchAfter": None,
            }

            data = await self._post_with_retry(self.BASE_URL, payload)

            hits = (
                data.get("queryResults", {})
                    .get("searchResponse", {})
                    .get("response", {})
            )
            docs = hits.get("docs", [])
            total = hits.get("numFound", 0)

            logger.info(
                "PEDS %s  offset=%d  page_hits=%d  total=%d",
                cpc_class, offset, len(docs), total,
            )

            if not docs:
                break

            for doc in docs:
                if yielded >= limit:
                    return
                yield doc
                yielded += 1

            offset += len(docs)
            if offset >= total:
                break

    async def fetch_office_actions(self, app_number: str) -> list[dict]:
        """
        Fetch the list of Office Action documents for a single application.

        Returns a list of document metadata dicts, each with keys:
          documentCode, documentDescription, mailDate, downloadURL
        """
        url = f"https://ped.uspto.gov/api/file-wrappers/{app_number}/documents"
        data = await self._get_with_retry(url)

        documents = data.get("documentBag", []) if isinstance(data, dict) else []

        # Filter to Office Action document codes
        oa_codes = {
            "CTNF",   # Non-Final Office Action
            "CTFR",   # Final Office Action
            "N/A.892",
            "892",    # Prior Art
            "NOA",    # Notice of Allowance (for cross-reference)
        }
        return [
            doc for doc in documents
            if doc.get("documentCode", "").upper() in oa_codes
        ]

    async def fetch_document_text(self, app_number: str, document_id: str) -> str:
        """
        Download and return the plain-text content of a specific OA document.

        PEDS serves documents as PDF; the API also provides a text endpoint
        at /api/file-wrappers/{app}/documents/{doc}/txt that returns
        extracted text (best-effort OCR).
        """
        url = (
            f"https://ped.uspto.gov/api/file-wrappers"
            f"/{app_number}/documents/{document_id}/txt"
        )
        for attempt in range(config.MAX_RETRIES):
            async with self._sem:
                try:
                    async with self._session.get(url) as resp:  # type: ignore[union-attr]
                        if resp.status == 200:
                            return await resp.text(errors="replace")
                        elif resp.status == 404:
                            return ""
                        elif resp.status in (429, 503):
                            wait = _backoff(attempt)
                            logger.warning(
                                "Rate limited on doc text %s/%s — sleeping %.1fs",
                                app_number, document_id, wait,
                            )
                            await asyncio.sleep(wait)
                        else:
                            logger.warning(
                                "Unexpected status %d for %s/%s",
                                resp.status, app_number, document_id,
                            )
                            return ""
                except aiohttp.ClientError as exc:
                    wait = _backoff(attempt)
                    logger.warning("ClientError fetching doc text: %s — retry in %.1fs", exc, wait)
                    await asyncio.sleep(wait)
        return ""

    # ------------------------------------------------------------------
    # Internal HTTP helpers
    # ------------------------------------------------------------------

    async def _post_with_retry(self, url: str, payload: dict) -> dict:
        for attempt in range(config.MAX_RETRIES):
            async with self._sem:
                try:
                    async with self._session.post(url, json=payload) as resp:  # type: ignore[union-attr]
                        if resp.status == 200:
                            return await _safe_json(resp)
                        elif resp.status in (429, 503):
                            wait = _backoff(attempt)
                            logger.warning("Rate limited — sleeping %.1fs", wait)
                            await asyncio.sleep(wait)
                        else:
                            logger.error("PEDS POST returned %d", resp.status)
                            return {}
                except aiohttp.ClientError as exc:
                    wait = _backoff(attempt)
                    logger.warning("ClientError: %s — retry in %.1fs", exc, wait)
                    await asyncio.sleep(wait)
        return {}

    async def _get_with_retry(self, url: str) -> dict | str:
        for attempt in range(config.MAX_RETRIES):
            async with self._sem:
                try:
                    async with self._session.get(url) as resp:  # type: ignore[union-attr]
                        if resp.status == 200:
                            ct = resp.headers.get("Content-Type", "")
                            if "json" in ct:
                                return await _safe_json(resp)
                            return await resp.text(errors="replace")
                        elif resp.status in (429, 503):
                            wait = _backoff(attempt)
                            await asyncio.sleep(wait)
                        elif resp.status == 404:
                            return {}
                        else:
                            return {}
                except aiohttp.ClientError as exc:
                    wait = _backoff(attempt)
                    logger.warning("GET error: %s — retry in %.1fs", exc, wait)
                    await asyncio.sleep(wait)
        return {}
