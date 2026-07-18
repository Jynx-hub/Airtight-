"""M4 harness tests — all stub mode, no network, green on a fresh clone."""

import json
import pathlib

import pytest

from airtight import Disclosure, LoopholeRecord, config
from agent.eval.harness import assert_no_overlap, run_ablation
from agent.memory import LoopholeStore

ROOT = pathlib.Path(__file__).resolve().parent.parent
DATA = ROOT / "data"


@pytest.fixture(autouse=True)
def force_stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")


def _disclosure(disc_id: str) -> Disclosure:
    return Disclosure.model_validate_json(
        (DATA / "fixtures" / "disclosures" / f"{disc_id}.json").read_text()
    )


def test_retrieval_is_deterministic_and_class_aware():
    store = LoopholeStore.load(DATA / "corpus" / "loopholes")
    assert len(store) >= 6
    disc = _disclosure("disc-0001")  # G06F
    first = store.retrieve(disc, k=3)
    second = store.retrieve(disc, k=3)
    assert [r.id for r in first] == [r.id for r in second]
    assert all(r.technology_class == "G06F" for r in first)  # class match outranks overlap


def test_empty_store_retrieves_nothing():
    assert LoopholeStore.empty().retrieve(_disclosure("disc-0001"), k=5) == []


def test_overlap_guard_fires_on_id_collision():
    store = LoopholeStore.load(DATA / "corpus" / "loopholes")
    leaked = LoopholeRecord(
        id="lh-w-001",  # same id as a corpus record
        pattern="x", claim_shape="y", technology_class="G06F", remedy="z", source="s",
    )
    with pytest.raises(RuntimeError, match="overlap guard"):
        assert_no_overlap(store, [leaked])


def test_overlap_guard_fires_on_near_duplicate_text():
    store = LoopholeStore.load(DATA / "corpus" / "loopholes")
    corpus_rec = store.records[0]
    leaked = LoopholeRecord(
        id="lh-c-999", pattern="x", claim_shape=corpus_rec.claim_shape,
        technology_class="G06F", remedy="z", source="s",
    )
    with pytest.raises(RuntimeError, match="overlap guard"):
        assert_no_overlap(store, [leaked])


def test_ablation_end_to_end_stub(tmp_path):
    results_path = run_ablation(DATA, k=3, runs=1, out_root=tmp_path)
    payload = json.loads(results_path.read_text())

    # 2 disclosures x 2 conditions
    assert len(payload["results"]) == 4
    assert payload["fingerprint"]["mode"] == "stub"
    assert payload["corpus_size"] >= 6
    assert (results_path.parent / "chart.html").exists()
    assert len(list((results_path.parent / "transcripts").glob("*.json"))) == 4

    # stub mode must NEVER fabricate a delta — both conditions score identically
    for pair in payload["pairs"]:
        assert pair["loopholes_caught_delta"] == 0
        assert pair["defect_count_delta"] == 0

    # transcripts carry the scaffold proof and the rendered slot difference
    transcript = json.loads(next((results_path.parent / "transcripts").glob("*warmed.json")).read_text())
    assert transcript["retrieved_ids"]
    assert transcript["scaffold_proof"]["warmed_slot"] != transcript["scaffold_proof"]["empty_slot"]
