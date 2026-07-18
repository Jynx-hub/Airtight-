"""Loophole memory: the store the M4 ablation flips between empty and warmed.

Day-one relevance is deterministic and boring — technology-class match, then
keyword overlap, then id tiebreak. Embeddings are an M3 upgrade that must keep
this interface.
"""

import json
import math
import re
from pathlib import Path
from typing import Sequence

from airtight import Disclosure, LoopholeRecord

_STOPWORDS = frozenset(
    "a an and are as at be by for from in is it of on or that the to with".split()
)


def tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


class LoopholeStore:
    def __init__(self, records: Sequence[LoopholeRecord]):
        self.records = list(records)

    @classmethod
    def load(cls, directory: Path | str) -> "LoopholeStore":
        records: list[LoopholeRecord] = []
        for path in sorted(Path(directory).glob("*.json")):
            data = json.loads(path.read_text())
            items = data if isinstance(data, list) else [data]
            records.extend(LoopholeRecord.model_validate(item) for item in items)
        return cls(records)

    @classmethod
    def empty(cls) -> "LoopholeStore":
        return cls([])

    def retrieve(self, disclosure: Disclosure, k: int = 5) -> list[LoopholeRecord]:
        return _retrieve(self.records, disclosure, k)

    # C3: the write API. The store used to be read-only by construction — which is exactly
    # why block D (ingest → memory) had no path to land records. add()/save() give it one;
    # dedup-by-id keeps a re-ingested document from duplicating records.
    def add(self, record: LoopholeRecord) -> bool:
        if any(r.id == record.id for r in self.records):
            return False
        self.records.append(record)
        return True

    def add_all(self, records: Sequence[LoopholeRecord]) -> int:
        return sum(self.add(r) for r in records)

    def save(self, directory: Path | str) -> Path:
        """Persist each record as <id>.json — the flat layout `load()` reads back."""
        directory = Path(directory)
        directory.mkdir(parents=True, exist_ok=True)
        for rec in self.records:
            (directory / f"{rec.id}.json").write_text(rec.model_dump_json(indent=2))
        return directory

    def __len__(self) -> int:
        return len(self.records)


def _rank(records: list[LoopholeRecord], disclosure: Disclosure) -> list[LoopholeRecord]:
    disc_tokens = tokens(f"{disclosure.title} {disclosure.summary} {disclosure.details}")

    # C2: IDF-weight the overlap instead of a raw token count. Real records carry 600+ char
    # `claim_shape` fields, so a raw count let the longest record win mechanically. IDF makes
    # common tokens (claim, method, device, system) count for almost nothing and rare,
    # distinctive tokens carry the match — so a short record sharing the disclosure's specific
    # vocabulary outranks a long one that merely overlaps on boilerplate. Deterministic.
    toks = [(rec, tokens(f"{rec.pattern} {rec.claim_shape} {rec.remedy}")) for rec in records]
    n = max(len(records), 1)
    df: dict[str, int] = {}
    for _, rt in toks:
        for t in rt:
            df[t] = df.get(t, 0) + 1

    def idf(t: str) -> float:
        return math.log(1 + n / df.get(t, 1))

    scored = {id(rec): sum(idf(t) for t in (rt & disc_tokens)) for rec, rt in toks}

    return sorted(
        records,
        key=lambda rec: (rec.technology_class == disclosure.technology_class,
                         scored[id(rec)], rec.id),
        reverse=True,
    )


def diversify_by_statute(ranked: list[LoopholeRecord], k: int) -> list[LoopholeRecord]:
    """Fill k by round-robin across statutes in ranked order, so the warmed set
    spans failure modes (§101/§102/§103/§112) instead of collapsing onto whichever
    one happened to win on keyword overlap. Deterministic: buckets keep ranked
    order; the round-robin visits them in first-seen order. This is the fix for
    the statute-blind retrieval that made a §103 disclosure get primed with §101."""
    buckets: dict[str, list[LoopholeRecord]] = {}
    for rec in ranked:  # ranked is already best-first, so each bucket is best-first
        buckets.setdefault(rec.statute or "?", []).append(rec)
    selected: list[LoopholeRecord] = []
    while len(selected) < k and any(buckets.values()):
        for recs in buckets.values():
            if recs and len(selected) < k:
                selected.append(recs.pop(0))
    return selected


def _retrieve(records: list[LoopholeRecord], disclosure: Disclosure, k: int) -> list[LoopholeRecord]:
    return diversify_by_statute(_rank(records, disclosure), k)
