"""
src/clients/patentsview_client.py
==================================
Async client for the PatentsView REST API.

Public endpoint — no authentication required.
Docs: https://patentsview.org/apis/api-query-language

PatentsView provides structured patent data derived from USPTO bulk data files.
We use it primarily to:
  1. Enumerate granted patents by CPC class (fast, structured)
  2. Pull claim text for a given patent number
  3. Cross-reference application numbers for PEDS lookup

Rate limit: ~45 requests/minute on the public tier.
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

# Fields we request per patent record
_PATENT_FIELDS = [
    "patent_id",
    "patent_number",
    "patent_title",
    "patent_date",
    "app_number",
    "app_date",
    "cpc_group_id",
    "claims_count",
]

# Fields from the /claims endpoint
_CLAIM_FIELDS = [
    "patent_id",
    "claim_number",
    "claim_text",
    "claim_sequence",
    "independent",
]


def _backoff(attempt: int) -> float:
    import random
    return min(config.BACKOFF_BASE ** attempt + random.uniform(0, 1), config.BACKOFF_MAX)


class PatentsViewClient:
    """
    Async client for the PatentsView public API.

    Usage::

        async with PatentsViewClient() as client:
            async for patent in client.search_by_cpc("G06F", limit=500):
                print(patent["patent_number"])
    """

    PATENTS_URL = config.PATENTSVIEW_BASE_URL
    CLAIMS_URL = "https://api.patentsview.org/claims/query"
    TIMEOUT = aiohttp.ClientTimeout(total=config.PATENTSVIEW_TIMEOUT)

    def __init__(self, semaphore: asyncio.Semaphore | None = None):
        self._sem = semaphore or asyncio.Semaphore(config.PATENTSVIEW_RATE_LIMIT)
        self._session: aiohttp.ClientSession | None = None

    async def __aenter__(self) -> "PatentsViewClient":
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
    # Public interface
    # ------------------------------------------------------------------

    async def search_by_cpc(
        self,
        cpc_class: str,
        limit: int = 1000,
        after_year: int = 2000,
    ) -> AsyncIterator[dict]:
        """
        Yield patent records for the given CPC class prefix.

        PatentsView uses a JSON query language:
          {"_begins": {"cpc_group_id": "G06F"}}
        """
        page = 1
        page_size = min(config.PATENTSVIEW_PAGE_SIZE, limit, 10_000)
        yielded = 0

        query = orjson.dumps({
            "_and": [
                {"_begins": {"cpc_group_id": cpc_class}},
                {"_gte": {"patent_date": f"{after_year}-01-01"}},
            ]
        }).decode()

        while yielded < limit:
            fetch_size = min(page_size, limit - yielded)
            params = {
                "q": query,
                "f": orjson.dumps(_PATENT_FIELDS).decode(),
                "o": orjson.dumps({
                    "page": page,
                    "per_page": fetch_size,
                    "sort": [{"patent_date": "desc"}],
                }).decode(),
            }

            data = await self._get_with_retry(self.PATENTS_URL, params)
            patents = data.get("patents") or []
            total = data.get("total_patent_count", 0)

            logger.info(
                "PatentsView %s  page=%d  hits=%d  total=%d",
                cpc_class, page, len(patents), total,
            )

            if not patents:
                break

            for patent in patents:
                if yielded >= limit:
                    return
                yield patent
                yielded += 1

            page += 1
            if yielded >= total:
                break

    async def fetch_claims(self, patent_id: str) -> list[dict]:
        """
        Fetch structured claim text for a given patent_id.

        Returns a list of claim dicts with keys:
          claim_number, claim_text, claim_sequence, independent
        """
        query = orjson.dumps({"patent_id": patent_id}).decode()
        params = {
            "q": query,
            "f": orjson.dumps(_CLAIM_FIELDS).decode(),
            "o": orjson.dumps({"per_page": 100}).decode(),
        }
        data = await self._get_with_retry(self.CLAIMS_URL, params)
        return data.get("claims") or []

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _get_with_retry(self, url: str, params: dict) -> dict:
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
                            logger.warning(
                                "PatentsView rate-limited — sleeping %.1fs", wait
                            )
                            await asyncio.sleep(wait)
                        elif resp.status == 404:
                            return {}
                        else:
                            logger.warning(
                                "PatentsView returned %d for %s", resp.status, url
                            )
                            return {}
                except aiohttp.ClientError as exc:
                    wait = _backoff(attempt)
                    logger.warning("ClientError: %s — retry in %.1fs", exc, wait)
                    await asyncio.sleep(wait)
        return {}
