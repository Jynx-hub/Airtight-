"""Why retrieval picked what it picked.

`agent/memory.py` returns records, not reasons — which is right for the engine
and useless for a panel trying to show that ranking is a mechanism rather than a
claim. This module recomputes the reasoning **read-only**, reusing memory's own
`_rank`, `diversify_by_statute` and BM25 constants so the two can't drift apart.

Nothing here may modify `agent/memory.py`. Retrieval has already been rewritten
twice (C1 statute diversification, C2 BM25 b=0.3) and CLAUDE.md requires it
frozen at a recorded SHA when the GPU window opens; a display concern is not a
reason to touch the file the ablation measures.

Records are matched to their scores by **object identity**, not by id. A store
can legitimately hold two records with the same id — `LoopholeStore.load` globs
a directory and flattens list files without deduping — and an id-keyed lookup is
last-wins, which would show one record's score against the other's text.
"""

import re

from agent.memory import (
    _BM25_B,
    _BM25_K1,
    _TRUSTED_CONFIDENCE,
    _corpus_stats,
    _rank,
    diversify_by_statute,
    tokens,
)
from airtight import Disclosure, LoopholeRecord

# The measured justification for deviating from BM25's literature-default b=0.75,
# transcribed from the table at agent/memory.py:26-40 so the panel can show the
# work. Lower b means less length normalisation; the win is disclosure
# specificity, not raw relevance.
B_SWEEP = {
    "parameter": "b",
    "chosen": _BM25_B,
    "literature_default": 0.75,
    "metric": "cross-disclosure Jaccard (lower = more disclosure-specific retrieval)",
    "rows": [
        {"b": 0.0, "jaccard": 0.102, "distinct": 27, "self_noise": "1/10", "bloat_promoted": "100%"},
        {"b": 0.3, "jaccard": 0.098, "distinct": 29, "self_noise": "1/10", "bloat_promoted": "97%"},
        {"b": 0.75, "jaccard": 0.104, "distinct": 29, "self_noise": "7/10", "bloat_promoted": "85%"},
        {"b": 1.0, "jaccard": 0.092, "distinct": 31, "self_noise": "9/10", "bloat_promoted": "77%"},
    ],
}

_APP_NO = re.compile(r"\d{6,}")


def _self_retrieval(disclosure: Disclosure, record: LoopholeRecord) -> bool:
    """True when a record was mined from the very application being drafted.

    Feeding a `data/real/` disclosure back through the ground-truth pool retrieves
    its own checklist — the examiner's actual rejections for that application. It
    reads as a spectacular result and is an artifact of demoing with corpus data.
    Flag it rather than let it quietly inflate the panel.
    """
    disc_app = set(_APP_NO.findall(disclosure.id))
    if not disc_app:
        return False
    return bool(disc_app & set(_APP_NO.findall(f"{record.id} {record.source}")))


def _scores(records: list[LoopholeRecord], disclosure: Disclosure) -> dict[int, dict]:
    """BM25 per record, keyed by id(record). Mirrors `_rank`'s inner scoring
    exactly — same tokenisation, same corpus stats, same rounding."""
    disc_tokens = tokens(f"{disclosure.title} {disclosure.summary} {disclosure.details}")
    docs = [tokens(f"{r.pattern} {r.claim_shape} {r.remedy}") for r in records]
    idf, avgdl = _corpus_stats(docs)

    out = {}
    for i, rec in enumerate(records):
        doc = docs[i]
        dl = len(doc) or 1
        overlap = sorted(doc & disc_tokens)
        matched = sum(idf[w] for w in overlap)
        score = matched * (_BM25_K1 + 1) / (1 + _BM25_K1 * (1 - _BM25_B + _BM25_B * dl / avgdl))
        out[id(rec)] = {
            "score": round(score, 4),
            "terms": sorted(overlap, key=lambda w: idf[w], reverse=True)[:8],
            "term_count": len(overlap),
            "doc_len": dl,
        }
    return out


def explain_retrieval(records: list[LoopholeRecord], disclosure: Disclosure, k: int = 5) -> dict:
    """The k picks with their reasons, plus the near-misses that lost.

    Selection is delegated to memory's own functions, so what's shown is what the
    drafting turn will actually be primed with — not a re-implementation that
    could disagree.
    """
    ranked = _rank(records, disclosure)
    picks = diversify_by_statute(ranked, k)
    scores = _scores(records, disclosure)
    picked_ids = {id(r) for r in picks}

    def row(rec: LoopholeRecord, rank_pos: int) -> dict:
        s = scores.get(id(rec), {})
        trusted = rec.extraction_confidence >= _TRUSTED_CONFIDENCE
        return {
            "id": rec.id,
            "statute": rec.statute or "?",
            "pattern": rec.pattern,
            "claim_shape": rec.claim_shape[:400],
            "remedy": rec.remedy[:400],
            "source": rec.source,
            "technology_class": rec.technology_class,
            "class_match": rec.technology_class == disclosure.technology_class,
            "confidence": rec.extraction_confidence,
            "trusted": trusted,
            "rank": rank_pos,
            "score": s.get("score", 0.0),
            "terms": s.get("terms", []),
            "term_count": s.get("term_count", 0),
            # Trusted records win a reserved slot per statute via the round-robin;
            # untrusted ones get no bucket and enter only by out-ranking a pick.
            "won_by": "statute slot" if trusted else "rank",
            "self_retrieval": _self_retrieval(disclosure, rec),
        }

    rank_of = {id(r): i for i, r in enumerate(ranked)}
    selected = [row(r, rank_of[id(r)]) for r in picks]
    runners_up = [row(r, rank_of[id(r)]) for r in ranked if id(r) not in picked_ids][:5]

    statutes = sorted({r["statute"] for r in selected})
    return {
        "k": k,
        "corpus_size": len(records),
        "selected": selected,
        "runners_up": runners_up,
        "statutes_covered": statutes,
        # The whole point of diversification: a §103 disclosure should not be
        # primed with five §103 records just because keyword overlap said so.
        "diversified": len(statutes) > 1,
        "self_retrieval_warning": any(r["self_retrieval"] for r in selected),
        "ranking": {
            "algorithm": "BM25 (BM25+ IDF), class-match first, id tiebreak",
            "k1": _BM25_K1,
            "b": _BM25_B,
            "trusted_confidence": _TRUSTED_CONFIDENCE,
        },
        "b_sweep": B_SWEEP,
    }
