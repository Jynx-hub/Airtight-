"""Episodic memory tests — including the M4 contamination regression."""

import json
import pathlib

import pytest

from airtight import Disclosure, Draft, config
from agent.episodes import (CompositeStore, DISTILL_CAP, Episode, EpisodeStore,
                            compress_run, material_defects)
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


def test_episode_write_gated_on_sink_and_env(tmp_path, monkeypatch):
    store = EpisodeStore([], tmp_path)
    monkeypatch.setattr(config, "EPISODES_ENABLED", False)
    draft_patent(DISC, episode_sink=store)  # sink but flag off -> no write
    assert len(store) == 0
    monkeypatch.setattr(config, "EPISODES_ENABLED", True)
    draft_patent(DISC)  # flag on but no sink -> no write (the ablation's guarantee)
    assert len(store) == 0
    draft_patent(DISC, episode_sink=store)  # sink AND flag on -> writes
    assert len(store) == 1
    assert len(list(tmp_path.rglob("*.json"))) == 1


# ---------- B3: bounded, clean distillation ----------

def test_material_defects_filters_junk_and_is_deterministic():
    critique = (
        "# Defects\nHere are the defects:\n"
        "- §112 antecedent-basis gap in claim 2\n"
        "-  \n"
        "* obvious over the cited art (§103)\n"
        "Some general prose with no statutory hook\n"
        "1. means-plus-function overbreadth in claim 5\n"
    )
    got = material_defects(critique)
    assert any("112" in d or "antecedent" in d for d in got)
    assert any("obvious" in d.lower() for d in got)
    assert any("means-plus-function" in d.lower() for d in got)
    assert not any(d.startswith("#") or d.startswith("Here are") or "general prose" in d for d in got)
    assert material_defects(critique) == got  # deterministic


def test_compress_run_bounds_and_cleans():
    d = Draft(disclosure_id=DISC.id, claims=["1. x"], specification="s", critique_notes=[
        "# Defects", "Here are the defects:", "- §112 antecedent basis in claim 1",
        "- obvious over Foo (§103)", "- indefinite term in claim 3",
        "- abstract idea under §101", "- means-plus-function in claim 5",
    ])
    ep = compress_run(DISC, [], d, "stub")
    synth = [r for r in ep.distilled if r.source.startswith("episode:")]
    assert 0 < len(synth) <= DISTILL_CAP  # capped, not one-per-line
    assert all(r.statute for r in synth)  # each carries a derived statute
    assert not any(r.pattern.lstrip("§").startswith("#") for r in synth)  # no headers became records


def test_compress_run_no_poison_in_stub():
    # stub critique carries no defect keyword -> zero synthetic records
    ep = compress_run(DISC, [], draft_patent(DISC), "stub")
    assert [r for r in ep.distilled if r.source.startswith("episode:")] == []


# ---------- B2: compounding ----------

def test_compounding_next_run_retrieves_prior_lesson(tmp_path, monkeypatch):
    monkeypatch.setattr(config, "EPISODES_ENABLED", True)
    store = EpisodeStore([], tmp_path)
    retrieved = LoopholeStore.load(DATA / "corpus" / "loopholes").retrieve(DISC, 2)
    d = Draft(disclosure_id=DISC.id, claims=["1"], specification="s",
              critique_notes=["- §112 antecedent basis in claim 1"])
    store.record(compress_run(DISC, retrieved, d, "live"))  # live => trusted next run
    reloaded = EpisodeStore.load(tmp_path)  # next run reloads from the <disc_id>/ subdir
    assert len(reloaded) == 1
    composite = CompositeStore(LoopholeStore.load(DATA / "corpus" / "loopholes"), reloaded, live_only=True)
    ids = [r.id for r in composite.retrieve(DISC, 10)]
    assert any(i.startswith(f"ep-{DISC.id}") for i in ids)  # the prior lesson is retrievable


def test_composite_store_merges_and_dedups(tmp_path):
    base = LoopholeStore.load(DATA / "corpus" / "loopholes")
    episodes = EpisodeStore([], tmp_path)
    episodes.record(compress_run(DISC, base.retrieve(DISC, 2), draft_patent(DISC), "stub"))
    composite = CompositeStore(base, episodes)
    ids = [r.id for r in composite.retrieve(DISC, 20)]
    assert len(ids) == len(set(ids))  # no dup ids
    assert len(composite) > len(base)


def test_ablation_uncontaminated_by_episodes(tmp_path, monkeypatch):
    """The core guarantee: a full episode store — even with EPISODES_ENABLED=true —
    must NOT change the ablation. The harness passes no sink, so no env flip writes."""
    monkeypatch.setattr(config, "EPISODES_ENABLED", True)  # the flag being on must not matter
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
