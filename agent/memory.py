"""Loophole memory: the store the M4 ablation flips between empty and warmed.

Day-one relevance is deterministic and boring — technology-class match, then
keyword overlap, then id tiebreak. Embeddings are an M3 upgrade that must keep
this interface.
"""

import json
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
        disc_tokens = tokens(f"{disclosure.title} {disclosure.summary} {disclosure.details}")

        def rank_key(rec: LoopholeRecord):
            overlap = len(tokens(f"{rec.pattern} {rec.claim_shape} {rec.remedy}") & disc_tokens)
            return (rec.technology_class == disclosure.technology_class, overlap, rec.id)

        return sorted(self.records, key=rank_key, reverse=True)[:k]

    def __len__(self) -> int:
        return len(self.records)
