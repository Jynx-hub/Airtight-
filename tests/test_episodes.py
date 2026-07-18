"""Episodic memory tests — including the M4 contamination regression."""

import json
import pathlib

import pytest

from airtight import Disclosure, config
from agent.episodes import CompositeStore, Episode, EpisodeStore, compress_run
from agent.eval.harness import run_ablation
from agent.loop import draft_patent
from agent.memory import LoopholeStore

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"
DISC = Disclosure.model_validate_json((DATA / "fixtures" / "disclosures" / "disc-0001.json").read_text())


@pytest.fixture(autouse=True)
def force_stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


def test_episode_roundtrips():
    ep = compress_run(DISC, LoopholeStore.load(DATA / "corpus" / "loopholes").retrieve(DISC, 3),
                      draft_patent(DISC), "stub")
    assert Episode.model_validate_json(ep.model_dump_json()) == ep
    assert ep.retrieved_ids and ep.distilled


def test_compress_run_captures_provenance():
    retrieved = LoopholeStore.load(DATA / "corpus" / "loopholes").retrieve(DISC, 2)
    draft = draft_patent(DISC, guardrails=retrieved)
    ep = compress_run(DISC, retrieved, draft, "stub")
    assert ep.retrieved_ids == [r.id for r in retrieved]
    assert ep.critique_findings == draft.critique_notes


def test_episode_store_retrieve_is_deterministic(tmp_path):
    store = EpisodeStore([], tmp_path)
    store.record(compress_run(DISC, LoopholeStore.load(DATA / "corpus" / "loopholes").retrieve(DISC, 3),
                              draft_patent(DISC), "stub"))
    first = [r.id for r in store.retrieve(DISC, 5)]
    assert first == [r.id for r in store.retrieve(DISC, 5)]
    assert all(r.technology_class == "G06F" for r in store.retrieve(DISC, 5))


def test_episode_sink_write_is_opt_in(tmp_path):
    store = EpisodeStore([], tmp_path)
    draft_patent(DISC)  # no sink
    assert len(store) == 0
    draft_patent(DISC, episode_sink=store)  # sink
    assert len(store) == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1


def test_composite_store_merges_and_dedups(tmp_path):
    base = LoopholeStore.load(DATA / "corpus" / "loopholes")
    episodes = EpisodeStore([], tmp_path)
    episodes.record(compress_run(DISC, base.retrieve(DISC, 2), draft_patent(DISC), "stub"))
    composite = CompositeStore(base, episodes)
    ids = [r.id for r in composite.retrieve(DISC, 20)]
    assert len(ids) == len(set(ids))  # no dup ids
    assert len(composite) > len(base)


def test_ablation_uncontaminated_by_episodes(tmp_path, monkeypatch):
    """The core guarantee: a full episode store must NOT change the ablation."""
    # baseline run, empty episode dir
    baseline = json.loads(run_ablation(DATA, k=3, runs=1, out_root=tmp_path / "a").read_text())

    # seed the episode dir heavily, then rerun
    episodes = EpisodeStore([], tmp_path / "eps")
    for _ in range(5):
        episodes.record(compress_run(DISC, LoopholeStore.load(DATA / "corpus" / "loopholes").retrieve(DISC, 5),
                                     draft_patent(DISC), "stub"))
    seeded = json.loads(run_ablation(DATA, k=3, runs=1, out_root=tmp_path / "b").read_text())

    assert all(p["loopholes_caught_delta"] == 0 for p in seeded["pairs"])
    assert all(p["defect_count_delta"] == 0 for p in seeded["pairs"])
    # retrieved ids identical between the two runs — episodes never entered the ablation
    assert [p["disclosure_id"] for p in baseline["pairs"]] == [p["disclosure_id"] for p in seeded["pairs"]]
