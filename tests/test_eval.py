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

    # every fixture disclosure x 2 conditions — derived, so adding a fixture can't
    # silently shrink what this asserts
    expected = 2 * len(list((DATA / "fixtures" / "disclosures").glob("*.json")))
    assert len(payload["results"]) == expected
    assert payload["fingerprint"]["mode"] == "stub"
    assert payload["fingerprint"]["split"] is None  # the fixtures tree is pre-split
    assert payload["corpus_size"] >= 6
    assert (results_path.parent / "chart.html").exists()
    assert len(list((results_path.parent / "transcripts").glob("*.json"))) == expected

    # stub mode must NEVER fabricate a delta — both conditions score identically
    for pair in payload["pairs"]:
        assert pair["loopholes_caught_delta"] == 0
        assert pair["defect_count_delta"] == 0

    # transcripts carry the scaffold proof and the rendered slot difference
    transcript = json.loads(next((results_path.parent / "transcripts").glob("*warmed.json")).read_text())
    assert transcript["retrieved_ids"]
    assert transcript["scaffold_proof"]["warmed_slot"] != transcript["scaffold_proof"]["empty_slot"]


# ---------- pooled layout (synthetic tree, so the split logic is tested deterministically) ----------

def _pool(tmp_path, n_pairs: int = 6, n_unpaired: int = 0) -> pathlib.Path:
    """A disclosures/ + checklists/ pool shaped like the puller's output."""
    root = tmp_path / "pool"
    (root / "disclosures").mkdir(parents=True)
    (root / "checklists").mkdir()
    base = _disclosure("disc-0001")
    for i in range(n_pairs + n_unpaired):
        disc_id = f"app-{i:04d}"
        (root / "disclosures" / f"{disc_id}.json").write_text(
            base.model_copy(update={"id": disc_id}).model_dump_json()
        )
        if i < n_pairs:
            # claim_shape must stay well clear of the 0.8 Jaccard guard across records
            rec = LoopholeRecord(
                id=f"oa-{disc_id}-c1", pattern=f"§101 pattern {i}",
                claim_shape=f"claim {i} " + " ".join(f"w{i}x{j}" for j in range(12)),
                technology_class="G06F", remedy=f"remedy {i}", source=f"source {i}",
            )
            (root / "checklists" / f"{disc_id}.json").write_text(
                json.dumps([rec.model_dump()])
            )
    return root


def test_pooled_split_is_deterministic_and_disjoint(tmp_path):
    from agent.eval.harness import holdout_split, load_pairs

    root = _pool(tmp_path)
    pairs, unpaired = load_pairs(root / "disclosures", root / "checklists")
    assert not unpaired

    first, corpus = holdout_split(pairs, n=2, seed=1234)
    again, _ = holdout_split(pairs, n=2, seed=1234)
    assert [d.id for d, _ in first] == [d.id for d, _ in again]

    held = {r.id for _, checklist in first for r in checklist}
    assert held and not (held & {r.id for r in corpus.records})
    # the split partitions the pool — no record is lost or double-counted
    assert len(held) + len(corpus) == sum(len(c) for _, c in pairs)


def test_pooled_skips_disclosures_without_checklists(tmp_path):
    root = _pool(tmp_path, n_pairs=4, n_unpaired=2)
    results_path = run_ablation(root, k=1, runs=1, out_root=tmp_path / "out", layout="pooled", n=2)
    split = json.loads(results_path.read_text())["fingerprint"]["split"]

    assert split["paired"] == 4
    assert len(split["unpaired_disclosure_ids"]) == 2  # visible, never silent
    assert not set(split["unpaired_disclosure_ids"]) & set(split["holdout_ids"])


def test_pooled_orphan_checklist_raises(tmp_path):
    root = _pool(tmp_path, n_pairs=3)
    (root / "checklists" / "app-9999.json").write_text("[]")  # no matching disclosure
    with pytest.raises(RuntimeError, match="no matching disclosure"):
        run_ablation(root, k=1, out_root=tmp_path / "out", layout="pooled", n=1)


def test_holdout_too_large_leaves_nothing_to_warm(tmp_path):
    root = _pool(tmp_path, n_pairs=3)
    with pytest.raises(RuntimeError, match="fewer than k"):
        run_ablation(root, k=1, out_root=tmp_path / "out", layout="pooled", n=3)


def test_fixtures_layout_tolerates_k_above_corpus_size(tmp_path):
    """The holdout guard is pooled-only — the fixtures corpus is a fixed file, so a
    large k just retrieves everything rather than being refused."""
    results_path = run_ablation(DATA, k=99, runs=1, out_root=tmp_path)
    assert json.loads(results_path.read_text())["results"]


def test_n_bounds_the_run(tmp_path):
    """The cost-control knob is itself tested — a metered run depends on it."""
    results_path = run_ablation(DATA, k=3, runs=1, out_root=tmp_path, n=1)
    assert len(json.loads(results_path.read_text())["results"]) == 2  # 1 disclosure x 2 conditions


def test_unknown_layout_raises(tmp_path):
    with pytest.raises(ValueError, match="unknown layout"):
        run_ablation(DATA, out_root=tmp_path, layout="bogus")


@pytest.mark.skipif(not (DATA / "real" / "checklists").exists(),
                    reason="data/real absent; it ships with the repo — restore it or run data/pull_uspto.py --groundtruth")
def test_real_pull_splits_cleanly():
    """The real holdout must not leak into the real warming corpus. No model calls."""
    from agent.eval.harness import holdout_split, load_pairs

    pairs, _ = load_pairs(DATA / "real" / "disclosures", DATA / "real" / "checklists")
    graded, corpus = holdout_split(pairs, n=10, seed=1234)
    for _, checklist in graded:
        assert_no_overlap(corpus, checklist)  # raises on id collision or >0.8 Jaccard


def test_ablation_uncontaminated_by_ingested(tmp_path, monkeypatch):
    """The D-side twin of test_ablation_uncontaminated_by_episodes.

    Ingested records are distilled from untrusted documents. If they could reach
    the warmed arm, the Track-1 number would be measuring the agent's own writing.
    The harness never reads config.INGESTED_DIR and never calls merged_store, so
    this holds by construction — assert it anyway, because 'by construction' is
    exactly the kind of guarantee a later refactor removes without noticing.
    """
    from airtight import LoopholeRecord, config as _config
    from agent.memory import LoopholeStore

    baseline = json.loads(run_ablation(DATA, k=3, runs=1, out_root=tmp_path / "a").read_text())

    ingested_dir = tmp_path / "ingested"
    store = LoopholeStore([], directory=ingested_dir)
    for i in range(20):
        store.save(LoopholeRecord(
            id=f"ing-noise-{i}", pattern=f"§101 fabricated pattern {i}",
            claim_shape="a module configured to perform the recited function",
            technology_class="G06F", remedy="noise", source="INGESTED attacker.pdf",
            extraction_confidence=0.3))
    monkeypatch.setattr(_config, "INGESTED_DIR", str(ingested_dir))

    seeded = json.loads(run_ablation(DATA, k=3, runs=1, out_root=tmp_path / "b").read_text())

    assert seeded["corpus_size"] == baseline["corpus_size"], "ingested records entered the corpus"
    assert all(p["loopholes_caught_delta"] == 0 for p in seeded["pairs"])
    assert ([r["loopholes_caught"] for r in seeded["results"]]
            == [r["loopholes_caught"] for r in baseline["results"]])


def test_extraction_confidence_cannot_perturb_the_prompt():
    """The ablation's scaffold proof rests on the guardrails slot rendering
    identically for identical records. A new shape field must not leak into it."""
    from airtight import LoopholeRecord
    from agent import loop

    kw = dict(id="x", pattern="§112 indefiniteness", claim_shape="a module configured to",
              technology_class="G06F", remedy="recite structure", source="s")
    ground_truth = LoopholeRecord(**kw)
    inferred = LoopholeRecord(**kw, extraction_confidence=0.3)
    assert ground_truth.extraction_confidence == 1.0
    assert loop.render_guardrails([ground_truth]) == loop.render_guardrails([inferred])
