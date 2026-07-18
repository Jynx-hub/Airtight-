"""Block C — retrieval: IDF-normalized overlap (C2) and the store write API (C3)."""

from airtight import Disclosure, LoopholeRecord
from agent.memory import LoopholeStore, _retrieve


def _rec(id_, pattern, claim_shape, tech="G06F"):
    return LoopholeRecord(id=id_, pattern=pattern, claim_shape=claim_shape,
                          technology_class=tech, remedy="r", source="s")


def test_c2_idf_overlap_beats_raw_length():
    """C2: a SHORT record sharing the disclosure's rare, distinctive term outranks a LONG
    record that overlaps only on boilerplate. Under the old raw token count the long record
    won mechanically (3 common matches > 1 rare match); IDF flips it."""
    disc = Disclosure(id="d", title="foldable zzhinge", inventors=["a"], technology_class="G06F",
                      summary="a device with a zzhinge", details="method system device zzhinge")
    common = "method system device comprising step wherein configured coupled"

    long_rec = _rec("long", "boilerplate", (common + " ") * 20)   # long, only common tokens
    short_rec = _rec("short", "zzhinge weakness", "zzhinge")       # short, the rare distinctive token
    fillers = [_rec(f"f{i}", "x", common) for i in range(12)]      # make the common tokens common (high df)

    ranked = _retrieve([long_rec, short_rec, *fillers], disc, k=len(fillers) + 2)
    assert ranked.index(short_rec) < ranked.index(long_rec)


def test_c3_write_api_add_dedups_and_saves(tmp_path):
    """C3: the store is no longer read-only — add() (dedup by id) + save() round-trip through load()."""
    store = LoopholeStore([])
    r1 = _rec("x1", "antecedent-basis gap", "said widget")
    assert store.add(r1) is True
    assert store.add(r1) is False          # same id → not duplicated
    assert store.add_all([_rec("x2", "p2", "c2"), r1]) == 1  # x2 added, r1 skipped
    assert len(store) == 2

    store.save(tmp_path)
    reloaded = LoopholeStore.load(tmp_path)
    assert {r.id for r in reloaded.records} == {"x1", "x2"}
