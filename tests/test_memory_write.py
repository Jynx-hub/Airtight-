"""C3: the LoopholeStore write API that D's ingest path persists through.

The guarantee that matters most here is negative — add() must not touch disk, and
a store the eval harness built must be structurally unable to persist at all.
"""

import pytest

from airtight import Disclosure, LoopholeRecord
from agent.memory import LoopholeStore, merged_store

DISC = Disclosure(id="d1", title="cache eviction", inventors=["x"], technology_class="G06F",
                  summary="evict entries by predicted recency", details="cache manager predicts access")


def _rec(rid, pattern="§112 indefiniteness", claim_shape="cache manager predicts access"):
    return LoopholeRecord(id=rid, pattern=pattern, claim_shape=claim_shape,
                          technology_class="G06F", remedy="r", source="s")


def test_add_dedups_by_id():
    store = LoopholeStore([_rec("a")])
    assert store.add(_rec("b")) is True
    assert store.add(_rec("a")) is False, "an existing id must not be added twice"
    assert len(store) == 2


def test_add_then_retrieve_surfaces_the_new_record():
    store = LoopholeStore([_rec("a")])
    store.add(_rec("zz-new"))
    assert "zz-new" in {r.id for r in store.retrieve(DISC, 5)}


def test_add_does_not_touch_disk(tmp_path):
    """The ablation-safety property: holding a record is not persisting it."""
    store = LoopholeStore([], directory=tmp_path)
    store.add(_rec("a"))
    assert list(tmp_path.glob("*.json")) == [], "add() wrote to disk; only save() may"


def test_save_requires_a_directory():
    with pytest.raises(RuntimeError, match="no directory"):
        LoopholeStore.empty().save(_rec("a"))


def test_harness_built_stores_cannot_persist():
    """empty() is the ablation's control arm — it must have nowhere to write."""
    assert LoopholeStore.empty().directory is None
    assert LoopholeStore([_rec("a")]).directory is None  # positional construction, as the harness does


def test_save_roundtrips_through_load(tmp_path):
    store = LoopholeStore([], directory=tmp_path)
    for rid in ("a", "b"):
        rec = _rec(rid)
        store.add(rec)
        store.save(rec)
    assert {r.id for r in LoopholeStore.load(tmp_path).records} == {"a", "b"}


def test_save_is_idempotent(tmp_path):
    """Re-saving the same record overwrites one file — it does not accumulate."""
    store = LoopholeStore([], directory=tmp_path)
    rec = _rec("a")
    store.save(rec)
    store.save(rec)
    assert len(list(tmp_path.glob("*.json"))) == 1
    assert len(LoopholeStore.load(tmp_path).records) == 1


def test_loaded_store_retains_its_directory(tmp_path):
    LoopholeStore([], directory=tmp_path).save(_rec("a"))
    assert LoopholeStore.load(tmp_path).directory == tmp_path


def test_load_of_missing_directory_is_empty(tmp_path):
    """An absent memory/ingested/ must degrade to an empty store, not raise."""
    store = LoopholeStore.load(tmp_path / "does-not-exist")
    assert len(store) == 0
    assert store.retrieve(DISC, 5) == []


def test_merged_store_dedups_first_wins():
    a = LoopholeStore([_rec("dup", pattern="§101 from base"), _rec("only-a")])
    b = LoopholeStore([_rec("dup", pattern="§103 from extra"), _rec("only-b")])
    merged = merged_store(a, b)
    assert {r.id for r in merged.records} == {"dup", "only-a", "only-b"}
    assert next(r for r in merged.records if r.id == "dup").statute == "101", "first store must win"


def test_merged_store_is_accepted_as_a_composite_base():
    """merged_store must return something CompositeStore can wrap — that is what
    lets ingested memory compose with episodes without editing agent/episodes.py."""
    from agent.episodes import CompositeStore, EpisodeStore

    composite = CompositeStore(merged_store(LoopholeStore([_rec("a")]), LoopholeStore([_rec("b")])),
                               EpisodeStore([]))
    assert {r.id for r in composite.retrieve(DISC, 5)} == {"a", "b"}


def test_duplicate_ids_are_scored_independently():
    """A store can hold two records with the same id — load() globs a directory
    and flattens list files without deduping. An id-keyed token cache is
    last-wins, which would score both copies with whichever loaded last."""
    off_topic = _rec("dup", claim_shape="unrelated widget bolt torque assembly")
    on_topic = _rec("dup", claim_shape="cache manager predicts access recency eviction")

    # Input order matters for this to discriminate. An id-keyed cache is
    # last-wins, so BOTH copies would be scored with on_topic's tokens, tie
    # exactly, and a stable sort would then leave off_topic (first in) ahead.
    # Scoring them independently is the only way on_topic comes out on top.
    order = [r.claim_shape for r in LoopholeStore([off_topic, on_topic]).retrieve(DISC, 2)]
    assert order.index(on_topic.claim_shape) < order.index(off_topic.claim_shape), \
        f"duplicates were scored with a shared token set: {order}"
