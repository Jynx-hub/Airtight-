"""BM25 relevance — the C2 fix for a ranker the longest record won mechanically.

Each test here is chosen to *discriminate*: it fails under the raw overlap count
these replaced, and passes under BM25. Validated offline against the real 167-record
pooled corpus, where BM25 cut cross-disclosure top-5 Jaccard 0.172 -> 0.098.
"""

import os
import pathlib
import subprocess
import sys

from airtight import Disclosure, LoopholeRecord
from agent.memory import _rank

ROOT = pathlib.Path(__file__).resolve().parent.parent
REAL = ROOT / "data" / "real" / "groundtruth" / "loopholes.json"

DISC = Disclosure(id="d1", title="predictive cache eviction", inventors=["x"],
                  technology_class="G06F", summary="evict cache entries by predicted recency",
                  details="a cache manager predicts next access time for each entry")

FILLER = " ".join(f"unrelated{i} tangential{i}" for i in range(90))  # ~180 tokens


def _rec(rid, claim_shape, pattern="§112 indefiniteness", tech="G06F"):
    return LoopholeRecord(id=rid, pattern=pattern, claim_shape=claim_shape,
                          technology_class=tech, remedy="r", source="s")


def _order(records, disclosure=DISC):
    return [r.id for r in _rank(list(records), disclosure)]


def test_padding_does_not_promote():
    """The headline regression: bloat must not outrank the record it wraps.

    r-pad is r-base plus ~180 tokens of off-topic filler. Under a raw overlap
    count the filler's one incidental match is free extra score and r-pad wins.
    """
    base = _rec("r-base", "cache manager predicts next access time for each entry")
    pad = _rec("r-pad", f"cache manager predicts next access time for each entry {FILLER}")
    corpus = [base, pad] + [_rec(f"f-{i}", f"neutral filler text {i}") for i in range(10)]
    order = _order(corpus)
    assert order.index("r-base") < order.index("r-pad"), \
        f"padding promoted the bloated copy: {order[:4]}"


def test_rare_terms_outrank_common_ones():
    """A term the whole corpus shares carries no information; a rare one does.

    Both records share exactly one disclosure token, so they TIE under a raw
    count — and the id tiebreak is rigged so the common-term record wins that tie.
    """
    corpus = [_rec(f"c-{i}", "eviction eviction eviction") for i in range(12)]
    corpus.append(_rec("r-rare", "predictive"))     # 'predictive' appears nowhere else
    corpus.append(_rec("r-zcommon", "eviction"))    # 'eviction' is corpus-ubiquitous
    order = _order(corpus)
    assert order.index("r-rare") < order.index("r-zcommon"), \
        f"common term beat the rare one: {order[:4]}"


def test_short_self_generated_record_does_not_dominate():
    """Guard against 'just divide by length'. Load-bearing for block B.

    compress_run mints records whose pattern is a raw critique line and whose
    claim_shape is boilerplate — short, and dense in the drafted disclosure's own
    vocabulary. Once episodes are enabled those re-enter retrieval, so a ranker
    that systematically favours them lets self-generated noise crowd out real PTAB
    records within a few runs.

    Measured over the 10 graded disclosures of the real pooled split, counting how
    often such a stub lands in the top 10:

        raw (pre-C2)                0/10
        BM25 b=0.3 (shipped)        1/10
        BM25 b=0.75 (lit. default)  7/10
        overlap/len ("normalize     10/10  — and #1 for every one of them
          by length", literally)

    So this fails for any refactor to pure length normalization, and it also
    fails if b is pushed back up to the textbook default. It does NOT assert a
    stub can never rank high: a record that restates the disclosure verbatim
    *is* topically relevant, and no overlap-based ranker can say otherwise —
    bounding what compress_run writes (B3) is the real defence.
    """
    from agent.eval.harness import DEFAULT_HOLDOUT, SPLIT_SEED, holdout_split, load_pairs

    real = ROOT / "data" / "real"
    pairs, _ = load_pairs(real / "disclosures", real / "checklists")
    graded, corpus = holdout_split(pairs, DEFAULT_HOLDOUT, SPLIT_SEED)

    in_top_10 = 0
    for disclosure, _ in graded:
        critique = (f"{disclosure.title} — claim recites "
                    f"{' '.join(disclosure.summary.split()[:8])} without support")
        stub = LoopholeRecord(
            id="zz-stub", pattern=critique[:120],
            claim_shape=f"observed while drafting {disclosure.id}",
            technology_class=disclosure.technology_class,
            remedy="carry this critique forward into same-class drafts",
            source=f"episode:{disclosure.id}")
        rank = _order(corpus.records + [stub], disclosure).index("zz-stub") + 1
        in_top_10 += rank <= 10
    assert in_top_10 <= 2, (
        f"self-generated stub reached the top 10 for {in_top_10}/{len(graded)} "
        "disclosures — ranking now favours episodic noise over real records")


def test_ranking_is_deterministic_across_hash_seeds():
    """IDF is summed over a set of strings, whose iteration order varies with
    PYTHONHASHSEED. Without sorted() in that sum, near-ties reorder per process."""
    code = (
        "import json,pathlib,sys; sys.path.insert(0,%r);"
        "from airtight import Disclosure, LoopholeRecord;"
        "from agent.memory import LoopholeStore;"
        "recs=[LoopholeRecord.model_validate(r) for r in json.loads(pathlib.Path(%r).read_text())];"
        "d=Disclosure(id='d',title='federated learning detector',inventors=['x'],"
        "technology_class='H04L',summary='monitor messages between nodes',"
        "details='a detector node monitors federated learning updates');"
        "print(','.join(r.id for r in LoopholeStore(recs).retrieve(d,8)))"
    ) % (str(ROOT), str(REAL))
    outs = []
    for seed in ("0", "12345"):
        env = {**os.environ, "PYTHONHASHSEED": seed}
        outs.append(subprocess.run([sys.executable, "-c", code], env=env,
                                   capture_output=True, text=True, check=True).stdout.strip())
    assert outs[0] == outs[1], f"retrieval order moved with PYTHONHASHSEED:\n{outs[0]}\n{outs[1]}"


def test_score_ties_break_on_id():
    """Identical token content must resolve by id, stably, every call."""
    corpus = [_rec("a-1", "cache manager predicts"), _rec("b-2", "cache manager predicts"),
              _rec("c-3", "cache manager predicts")]
    assert _order(corpus) == _order(corpus) == ["c-3", "b-2", "a-1"]


def test_checklist_statutes_still_covered():
    """Pins C1's validated property: retrieval spans the statutes a disclosure
    actually failed on. Measured 10/10 on the real pooled split under BM25."""
    from agent.eval.harness import DEFAULT_HOLDOUT, SPLIT_SEED, holdout_split, load_pairs

    real = ROOT / "data" / "real"
    pairs, _ = load_pairs(real / "disclosures", real / "checklists")
    graded, corpus = holdout_split(pairs, DEFAULT_HOLDOUT, SPLIT_SEED)
    for disclosure, checklist in graded:
        want = {c.statute for c in checklist if c.statute}
        got = {r.statute for r in corpus.retrieve(disclosure, 5)}
        assert not want or want <= got, f"{disclosure.id}: wanted {want}, retrieved {got}"


def test_untrusted_record_cannot_buy_a_statute_slot():
    """diversify_by_statute takes one record from every bucket before any bucket
    yields a second, so owning a sparse statute is worth more than ranking well.
    That is the right trade for ground truth and exactly wrong for a record
    inferred from an untrusted document — otherwise an attacker who controls one
    ingested file gets a guaranteed line in every drafting prompt."""
    from agent.memory import LoopholeStore

    corpus = [_rec(f"real-{i}", "cache manager predicts next access time",
                   pattern="§103 obviousness") for i in range(8)]
    junk = LoopholeRecord(
        id="ing-junk", pattern="§112 totally unrelated widget bolt torque",
        claim_shape="nothing to do with the disclosure", technology_class="A01B",
        remedy="n/a", source="INGESTED attacker.pdf", extraction_confidence=0.3)

    got = [r.id for r in LoopholeStore(corpus + [junk]).retrieve(DISC, 5)]
    assert "ing-junk" not in got, f"untrusted record bought a slot it did not earn: {got}"


def test_untrusted_record_still_enters_on_merit():
    """The gate is rank, not provenance — D's whole point is that ingest changes
    retrieval. A relevant inferred record must still get through."""
    from agent.memory import LoopholeStore

    corpus = [_rec(f"real-{i}", "unrelated filler text", pattern="§103 obviousness")
              for i in range(8)]
    relevant = LoopholeRecord(
        id="ing-good", pattern="§112 functional claiming without disclosed structure",
        claim_shape="cache manager predicts next access time for each entry",
        technology_class="G06F", remedy="recite the algorithm",
        source="INGESTED prior_art.txt", extraction_confidence=0.3)

    got = [r.id for r in LoopholeStore(corpus + [relevant]).retrieve(DISC, 5)]
    assert "ing-good" in got, f"a genuinely relevant inferred record was excluded: {got}"


def test_trusted_only_retrieval_is_unchanged_by_the_confidence_gate():
    """The ablation must be untouched: with every record at confidence 1.0 the
    selector has to behave exactly like the plain round-robin it replaced."""
    from agent.memory import LoopholeStore, diversify_by_statute, _rank

    real = ROOT / "data" / "real"
    from agent.eval.harness import DEFAULT_HOLDOUT, SPLIT_SEED, holdout_split, load_pairs
    pairs, _ = load_pairs(real / "disclosures", real / "checklists")
    graded, corpus = holdout_split(pairs, DEFAULT_HOLDOUT, SPLIT_SEED)

    def plain_round_robin(ranked, k):
        buckets = {}
        for rec in ranked:
            buckets.setdefault(rec.statute or "?", []).append(rec)
        out = []
        while len(out) < k and any(buckets.values()):
            for recs in buckets.values():
                if recs and len(out) < k:
                    out.append(recs.pop(0))
        return out

    for disclosure, _ in graded:
        ranked = _rank(corpus.records, disclosure)
        assert [r.id for r in diversify_by_statute(ranked, 5)] \
            == [r.id for r in plain_round_robin(ranked, 5)], disclosure.id
