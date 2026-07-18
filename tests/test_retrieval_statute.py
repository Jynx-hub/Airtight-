"""The statute-aware retrieval fix — the thing that gated the Track-1 delta.

Statute-blind top-k could return all-one-statute for a disclosure whose real
failure mode was another; retrieval now spreads the k across statutes.
"""

import pathlib

from airtight import Disclosure, LoopholeRecord
from airtight.shapes import statute_of
from agent.memory import LoopholeStore

DISC = Disclosure(id="d1", title="federated learning detector node", inventors=["x"],
                  technology_class="H04L", summary="monitor messages between client nodes",
                  details="a detector node monitors federated learning updates")


def _rec(rid, pattern, overlap_bait=""):
    # claim_shape carries the keyword-overlap bait so we control ranking
    return LoopholeRecord(id=rid, pattern=pattern, claim_shape=f"detector node monitors {overlap_bait}",
                          technology_class="H04L", remedy="r", source="s")


def test_statute_derived_from_pattern():
    assert statute_of("§103 — obviousness over prior art") == "103"
    assert statute_of("means-plus-function", "§112(f) indefiniteness") == "112"
    assert statute_of("antecedent-basis gap") == ""  # no statute → empty
    r = LoopholeRecord(id="x", pattern="§101 — abstract idea", claim_shape="c",
                       technology_class="G06F", remedy="r", source="s")
    assert r.statute == "101"  # populated by the validator


def test_retrieval_spreads_across_statutes_not_one():
    # 4x §101 with HIGH overlap + 1x §103 with lower overlap. Statute-blind top-4
    # would return 4x §101 and miss §103 entirely; diversified must surface §103.
    corpus = LoopholeStore([
        _rec("a1", "§101 — abstract idea", "federated learning updates messages nodes"),
        _rec("a2", "§101 — abstract idea", "federated learning updates messages"),
        _rec("a3", "§101 — abstract idea", "federated learning updates"),
        _rec("a4", "§101 — abstract idea", "federated learning"),
        _rec("b1", "§103 — obviousness over prior art", "detector"),
    ])
    got = corpus.retrieve(DISC, k=4)
    statutes = {r.statute for r in got}
    assert "103" in statutes, "diversified retrieval must surface the §103 pattern"
    assert "101" in statutes  # the high-overlap statute still represented


def test_retrieval_deterministic():
    corpus = LoopholeStore([
        _rec("a1", "§101 — abstract idea", "federated"),
        _rec("b1", "§103 — obviousness", "learning"),
        _rec("c1", "§112 — indefiniteness", "detector"),
    ])
    assert [r.id for r in corpus.retrieve(DISC, 3)] == [r.id for r in corpus.retrieve(DISC, 3)]
