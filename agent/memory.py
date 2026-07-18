"""Loophole memory: the store the M4 ablation flips between empty and warmed.

Relevance is deterministic and boring — technology-class match, then BM25 over
the record text, then id tiebreak. Embeddings are an M3 upgrade that must keep
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

# BM25. k1 damps the reward for piling on more evidence; b sets how hard document
# length is normalized.
#
# b is 0.3, not the literature-default 0.75, and the deviation is measured. Swept
# against the real 167-record pooled corpus, b controls a genuine trade-off:
#
#   b     cross-disc Jaccard   distinct   self-noise stub in top-10   bloat promoted
#   0.0        0.102              27              1/10                    100%
#   0.3        0.098              29              1/10                     97%
#   0.75       0.104              29              7/10                     85%
#   1.0        0.092              31              9/10                     77%
#
# The disclosure-specificity win — the metric the ablation actually rewards — comes
# from IDF, not from length normalization: it is already there at b=0. What extra b
# buys is resistance to a *bloated* record, and what it costs is resistance to a
# short one densely packed with the disclosure's own vocabulary. That second shape
# is exactly what agent/episodes.py:compress_run mints, so a high b would make
# self-generated lessons outrank real PTAB records the moment episodes are enabled.
# b=0.3 keeps the Jaccard win and the noise resistance; it gives up most of the
# bloat resistance, which is the weakest of the three signals (a record holding two
# real patterns genuinely *is* relevant to queries matching either).
_BM25_K1 = 1.2
_BM25_B = 0.3

# Records at or above this carry a statute bucket in diversify_by_statute; below
# it they must earn their slot on rank. Ground truth is 1.0 (LoopholeRecord's
# default); agent/distill.py mints ingested records at 0.3.
_TRUSTED_CONFIDENCE = 1.0


def tokens(text: str) -> set[str]:
    # Also imported by agent/eval/harness.py, where it drives the leakage guard's
    # Jaccard threshold. Weighting belongs in the ranker, not in here — changing
    # this function silently moves that threshold too.
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if t not in _STOPWORDS}


class LoopholeStore:
    def __init__(self, records: Sequence[LoopholeRecord], directory: Path | str | None = None):
        # `records` stays a plain list: CompositeStore (agent/episodes.py) and the
        # harness's overlap guard both reach for `.records` directly.
        # `directory` is keyword-defaulted and must stay the second parameter —
        # LoopholeStore(corpus) is constructed positionally in the harness.
        self.records = list(records)
        self.directory = Path(directory) if directory else None

    @classmethod
    def load(cls, directory: Path | str) -> "LoopholeStore":
        records: list[LoopholeRecord] = []
        for path in sorted(Path(directory).glob("*.json")):
            data = json.loads(path.read_text())
            items = data if isinstance(data, list) else [data]
            records.extend(LoopholeRecord.model_validate(item) for item in items)
        return cls(records, directory)

    @classmethod
    def empty(cls) -> "LoopholeStore":
        # Deliberately no directory: the ablation's control arm is structurally
        # incapable of persisting anything.
        return cls([])

    def retrieve(self, disclosure: Disclosure, k: int = 5) -> list[LoopholeRecord]:
        return _retrieve(self.records, disclosure, k)

    def add(self, record: LoopholeRecord) -> bool:
        """Hold a record in memory. Zero I/O — save() is the only thing that writes.

        Dedups by id with the incumbent winning, matching CompositeStore's
        `merged.setdefault`, so the two merge paths can't disagree about which
        copy of an id survives.
        """
        if any(r.id == record.id for r in self.records):
            return False
        self.records.append(record)
        return True

    def save(self, record: LoopholeRecord) -> Path:
        if self.directory is None:
            raise RuntimeError("LoopholeStore has no directory to persist to")
        # data/ is the graded, git-tracked corpus the ablation measures. Agent-
        # generated records must never land there — a single `--memory-dir
        # data/corpus/loopholes` would otherwise commit a confidence-0.3 record
        # as ground truth and silently contaminate every later run.
        resolved = self.directory.resolve()
        data_root = (Path(__file__).resolve().parent.parent / "data").resolve()
        if resolved == data_root or data_root in resolved.parents:
            raise RuntimeError(
                f"refusing to write agent-generated records into the graded corpus: {resolved}. "
                "data/ is the tracked ground truth the ablation measures; use memory/ instead."
            )
        self.directory.mkdir(parents=True, exist_ok=True)
        path = self.directory / f"{record.id}.json"  # flat — load() globs, it doesn't recurse
        path.write_text(record.model_dump_json(indent=2))
        return path

    def __len__(self) -> int:
        return len(self.records)


def merged_store(*stores: LoopholeStore) -> LoopholeStore:
    """One store over several, id-deduped, first store wins.

    Returns a plain LoopholeStore, so the result still satisfies CompositeStore's
    `base` contract (which reaches for `.records`). That is what lets an ingested
    corpus compose with episodes without touching agent/episodes.py.
    """
    merged: dict[str, LoopholeRecord] = {}
    for store in stores:
        for rec in store.records:
            merged.setdefault(rec.id, rec)
    return LoopholeStore(list(merged.values()))


def _corpus_stats(docs: list[set[str]]) -> tuple[dict[str, float], float]:
    """Per-term IDF and mean document length, over this store.

    The log(1 + …) form is BM25+. The classic Robertson IDF goes negative for a
    term appearing in more than half the corpus, which would make a common word
    actively *hurt* a record rather than merely not helping it.
    """
    n = len(docs) or 1
    df: dict[str, int] = {}
    for doc in docs:
        for word in doc:
            df[word] = df.get(word, 0) + 1
    idf = {w: math.log(1 + (n - d + 0.5) / (d + 0.5)) for w, d in df.items()}
    avgdl = sum(len(d) for d in docs) / n or 1.0
    return idf, avgdl


def _rank(records: list[LoopholeRecord], disclosure: Disclosure) -> list[LoopholeRecord]:
    """Class match first, then BM25 relevance, then id.

    BM25 replaced a raw overlap count that the longest record won mechanically —
    real records carry 600+ char claim_shape fields, so the ranker was partly
    handing the same big records to every disclosure. Note the score is
    corpus-relative: IDF is computed over `records`, so the same record scores
    differently inside a different store. That is correct BM25, and it leaves the
    ablation alone — both arms use fixed stores, and the empty arm retrieves [].
    """
    disc_tokens = tokens(f"{disclosure.title} {disclosure.summary} {disclosure.details}")
    # Keyed by POSITION, not by rec.id. A store can legitimately hold two records
    # with the same id — load() globs a directory and flattens list files without
    # deduping — and an id-keyed cache is last-wins, so both copies would be scored
    # with whichever text happened to load last. The overlap count this replaced
    # tokenized inline per record and was immune; keep that property.
    docs = [tokens(f"{rec.pattern} {rec.claim_shape} {rec.remedy}") for rec in records]
    idf, avgdl = _corpus_stats(docs)

    def rank_key(indexed: tuple[int, LoopholeRecord]):
        i, rec = indexed
        doc = docs[i]
        dl = len(doc) or 1
        # sorted() keeps the float sum order-stable: set iteration order for
        # strings varies with PYTHONHASHSEED, which would otherwise move near-ties.
        matched = sum(idf[w] for w in sorted(doc & disc_tokens))
        score = matched * (_BM25_K1 + 1) / (1 + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
        # round() so a libm difference across platforms can't reorder near-ties;
        # genuine ties then fall through to the id, as they always have.
        return (rec.technology_class == disclosure.technology_class, round(score, 6), rec.id)

    return [rec for _, rec in sorted(enumerate(records), key=rank_key, reverse=True)]


def diversify_by_statute(ranked: list[LoopholeRecord], k: int) -> list[LoopholeRecord]:
    """Fill k by round-robin across statutes in ranked order, so the warmed set
    spans failure modes (§101/§102/§103/§112) instead of collapsing onto whichever
    one happened to win on keyword overlap. Deterministic: buckets keep ranked
    order; the round-robin visits them in first-seen order. This is the fix for
    the statute-blind retrieval that made a §103 disclosure get primed with §101.

    **Only trusted records get a bucket.** The round-robin takes one record from
    every bucket before any bucket yields a second, so owning a sparse bucket is
    worth more than ranking well — a record alone in its statute takes a top-k
    slot whatever its score. That is the intended trade for ground truth, and
    exactly wrong for a record inferred from an untrusted document: measured, an
    ingested record with zero token overlap and the wrong CPC class still took a
    slot, evicting a real PTAB record. Low-confidence records therefore compete on
    rank alone — they enter only by out-ranking a record the round-robin picked.

    When every record is trusted (the ablation, and any pure-corpus retrieval)
    this is byte-identical to the plain round-robin; the merge below is skipped.
    """
    buckets: dict[str, list[int]] = {}  # statute -> positions in `ranked`
    untrusted: list[int] = []
    for i, rec in enumerate(ranked):  # ranked is best-first, so each bucket is too
        if rec.extraction_confidence >= _TRUSTED_CONFIDENCE:
            buckets.setdefault(rec.statute or "?", []).append(i)
        else:
            untrusted.append(i)

    selected: list[int] = []
    while len(selected) < k and any(buckets.values()):
        for positions in buckets.values():
            if positions and len(selected) < k:
                selected.append(positions.pop(0))

    if untrusted:
        # Merge on rank: an inferred record displaces a diversified pick only by
        # out-ranking it. Ordering falls back to rank order here rather than
        # round-robin order — deterministic either way.
        selected = sorted(selected + untrusted)[:k]
    return [ranked[i] for i in selected]


def _retrieve(records: list[LoopholeRecord], disclosure: Disclosure, k: int) -> list[LoopholeRecord]:
    return diversify_by_statute(_rank(records, disclosure), k)
