"""M4 ablation harness — the Track-1 proof.

Same disclosures, same model, same prompt scaffold, same decoding params; the
only variable is what the memory store retrieves. Every run writes a full audit
trail (config fingerprint, per-turn transcripts, scaffold proof, overlap-guard
report) so the delta can be re-derived, not taken on faith.
"""

import hashlib
import json
import subprocess
import time
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

from airtight import Disclosure, EvalResult, LoopholeRecord, config
from agent import loop
from agent.eval import judge
from agent.eval.chart import write_chart
from agent.memory import LoopholeStore, tokens

# Default: reasoning-on, uncapped drafting (the intended experiment, per ARCHITECTURE).
DRAFT_GEN = {"temperature": 0.0, "seed": 1234}
# --fast: reasoning off + capped drafts. An uncapped reasoning-on draft ran ~50s /
# ~7k tokens, making a full run 15+ min; this trades draft depth for a quick,
# still-valid ablation (same setting on both arms). Recorded in the fingerprint.
FAST_DRAFT_GEN = {**DRAFT_GEN, "max_tokens": 1100,
                  "extra_body": {"chat_template_kwargs": {"enable_thinking": False}}}
OVERLAP_JACCARD_MAX = 0.8
# Pooled layout: how many disclosures are held out for grading. The rest supply the
# warming corpus. 10 of 38 leaves a corpus ~11x k=5 while keeping a live run short.
DEFAULT_HOLDOUT = 10
SPLIT_SEED = 1234


# ---------- loading (Person 1 fills these directories; layout is the contract) ----------

def load_disclosures(directory: Path) -> list[Disclosure]:
    return [
        Disclosure.model_validate_json(p.read_text())
        for p in sorted(Path(directory).glob("*.json"))
    ]


def load_checklist(directory: Path, disclosure_id: str) -> list[LoopholeRecord]:
    path = Path(directory) / f"{disclosure_id}.json"
    return [LoopholeRecord.model_validate(item) for item in json.loads(path.read_text())]


# ---------- the pooled layout (data/real is one undivided pool; fixtures/ is pre-split) ----------

def load_pairs(disc_dir: Path, chk_dir: Path) -> tuple[list[tuple[Disclosure, list[LoopholeRecord]]], list[str]]:
    """Disclosures that actually drew a rejection, paired with their checklist.

    The puller writes a checklist only for disclosures that have defects — an empty
    one scores 0-of-0 and would read as a *passing* ablation — so a missing file is a
    real property of the pull (12 of the 50 in data/real), not a broken one. Skipping
    them is right; skipping them quietly is not, so the skipped ids ride out in the
    fingerprint. The reverse (a checklist with no disclosure) means a truncated pull.
    """
    disc_ids = {p.stem for p in Path(disc_dir).glob("*.json")}
    orphans = sorted({p.stem for p in Path(chk_dir).glob("*.json")} - disc_ids)
    if orphans:
        raise RuntimeError(f"checklists with no matching disclosure under {disc_dir}: {orphans}")

    pairs, unpaired = [], []
    for disclosure in load_disclosures(disc_dir):
        if (Path(chk_dir) / f"{disclosure.id}.json").exists():
            pairs.append((disclosure, load_checklist(chk_dir, disclosure.id)))
        else:
            unpaired.append(disclosure.id)
    return pairs, unpaired


def holdout_split(
    pairs: list[tuple[Disclosure, list[LoopholeRecord]]], n: int, seed: int
) -> tuple[list[tuple[Disclosure, list[LoopholeRecord]]], LoopholeStore]:
    """Split the pool into a graded holdout and the warming corpus it was held out of.

    Ordering is sha256(seed|id), not random.sample: the same (seed, n) picks the same
    disclosures on any platform, and a later, larger pull *interleaves* new ids rather
    than reshuffling ones already published in a results file.

    The corpus is every *other* application's records. It is deliberately not built from
    data/real/groundtruth/loopholes.json, which is the union of all 38 checklists and
    would hand the warmed arm the exact records it is graded on — assert_no_overlap
    would refuse it, correctly.
    """
    ranked = sorted(pairs, key=lambda p: hashlib.sha256(f"{seed}|{p[0].id}".encode()).hexdigest())
    graded = sorted(ranked[:n], key=lambda p: p[0].id)
    held = {d.id for d, _ in graded}
    corpus = [rec for d, checklist in pairs if d.id not in held for rec in checklist]
    return graded, LoopholeStore(corpus)


# ---------- guards & provenance ----------

def assert_no_overlap(corpus: LoopholeStore, checklist: list[LoopholeRecord]) -> dict:
    """Hard precondition: the held-out checklist must not leak into the warming corpus."""
    corpus_ids = {r.id for r in corpus.records}
    report = {"id_collisions": [], "jaccard_flags": []}
    for item in checklist:
        if item.id in corpus_ids:
            report["id_collisions"].append(item.id)
        item_tokens = tokens(item.claim_shape)
        for rec in corpus.records:
            rec_tokens = tokens(rec.claim_shape)
            union = item_tokens | rec_tokens
            jac = len(item_tokens & rec_tokens) / len(union) if union else 0.0
            if jac > OVERLAP_JACCARD_MAX:
                report["jaccard_flags"].append(
                    {"checklist": item.id, "corpus": rec.id, "jaccard": round(jac, 2)}
                )
    if report["id_collisions"] or report["jaccard_flags"]:
        raise RuntimeError(f"overlap guard failed — checklist leaks into warming corpus: {report}")
    return report


def scaffold_proof(retrieved: list[LoopholeRecord]) -> dict:
    """Record that both conditions render the identical templates, differing only
    inside the {guardrails} slot."""
    warmed_slot = loop.render_guardrails(retrieved)
    proof = {"templates_sha256": {}, "empty_slot": loop.GUARDRAILS_EMPTY, "warmed_slot": warmed_slot}
    for name in ("PLAN_SYSTEM", "DRAFT_SYSTEM", "CRITIQUE_SYSTEM", "REVISE_SYSTEM"):
        template = getattr(loop, name)
        proof["templates_sha256"][name] = hashlib.sha256(template.encode()).hexdigest()
        if "{guardrails}" in template:
            empty_r = template.format(guardrails=loop.GUARDRAILS_EMPTY)
            warmed_r = template.format(guardrails=warmed_slot)
            assert empty_r.replace(loop.GUARDRAILS_EMPTY, " ") == warmed_r.replace(
                warmed_slot, " "
            ), f"{name}: conditions differ outside the guardrails slot"
    return proof


def config_fingerprint(k: int, runs: int, draft_gen: dict = DRAFT_GEN, split: dict | None = None,
                       revise_rounds: int = 1) -> dict:
    try:
        git_sha = subprocess.run(
            ["git", "rev-parse", "HEAD"], capture_output=True, text=True, cwd=Path(__file__).parent
        ).stdout.strip()
    except OSError:
        git_sha = "unknown"
    return {
        "timestamp": datetime.now().astimezone().isoformat(timespec="seconds"),
        "mode": config.MODE,
        "model": config.MODEL,
        "base_url_host": urlparse(config.BASE_URL).hostname or "(none)",
        "draft_gen": draft_gen,
        "judge_gen": judge.JUDGE_GEN,
        "k": k,
        "runs": runs,
        "revise_rounds": revise_rounds,
        "split": split,  # None for the pre-split fixtures layout
        "git_sha": git_sha,
        "prompt_sha256": {
            "PLAN_SYSTEM": hashlib.sha256(loop.PLAN_SYSTEM.encode()).hexdigest(),
            "DRAFT_SYSTEM": hashlib.sha256(loop.DRAFT_SYSTEM.encode()).hexdigest(),
            "CRITIQUE_SYSTEM": hashlib.sha256(loop.CRITIQUE_SYSTEM.encode()).hexdigest(),
            "REVISE_SYSTEM": hashlib.sha256(loop.REVISE_SYSTEM.encode()).hexdigest(),
            "CHECKLIST_SYSTEM": hashlib.sha256(judge.CHECKLIST_SYSTEM.encode()).hexdigest(),
            "DEFECT_SYSTEM": hashlib.sha256(judge.DEFECT_SYSTEM.encode()).hexdigest(),
        },
    }


# ---------- the ablation ----------

def run_condition(
    disclosure: Disclosure,
    store: LoopholeStore,
    checklist: list[LoopholeRecord],
    condition: str,
    k: int,
    transcript_dir: Path,
    run_idx: int,
    draft_gen: dict = DRAFT_GEN,
    revise_rounds: int = 1,
) -> EvalResult:
    retrieved = store.retrieve(disclosure, k)  # executes in BOTH conditions (empty store -> [])
    transcript: list = []

    t0 = time.perf_counter()
    draft = loop.draft_patent(disclosure, guardrails=retrieved, transcript=transcript,
                              max_revise_rounds=revise_rounds, **draft_gen)
    seconds = time.perf_counter() - t0

    claims_text = "\n".join(f"{i + 1}. {c}" for i, c in enumerate(draft.claims))
    verdicts = judge.score_checklist(claims_text, checklist)
    defects = judge.count_defects(claims_text, draft.specification)

    result = EvalResult(
        disclosure_id=disclosure.id,
        condition=condition,
        loopholes_caught=sum(v.closed for v in verdicts),
        checklist_size=len(checklist),
        drafting_seconds=round(seconds, 2),
        defect_count=len(defects),
    )

    record = {
        "run": run_idx,
        "condition": condition,
        "disclosure_id": disclosure.id,
        "retrieved_ids": [r.id for r in retrieved],
        "scaffold_proof": scaffold_proof(retrieved),
        "transcript": transcript,
        "verdicts": [v.model_dump() for v in verdicts],
        "defects": [d.model_dump() for d in defects],
        "result": result.model_dump(),
    }
    out = transcript_dir / f"run{run_idx}-{disclosure.id}-{condition}.json"
    out.write_text(json.dumps(record, indent=2))
    return result


def run_ablation(data_root: Path, k: int = 5, runs: int = 1, out_root: Path = Path("results/ablation"),
                 draft_gen: dict = DRAFT_GEN, layout: str = "fixtures",
                 n: int | None = None, seed: int = SPLIT_SEED,
                 deadline: float | None = None, revise_rounds: int = 1) -> Path:
    """Run the paired empty-vs-warmed ablation over every graded disclosure.

    Two layouts. "fixtures" is the pre-split curated tree (data/fixtures/disclosures +
    data/groundtruth/checklists + data/corpus/loopholes) and is the default, so the
    stub path is unchanged. "pooled" is one undivided pool (disclosures/ + checklists/,
    as data/real is written) which gets split here into a graded holdout and the
    warming corpus that excludes it.
    """
    data_root = Path(data_root)
    if layout == "fixtures":
        graded = [(d, load_checklist(data_root / "groundtruth" / "checklists", d.id))
                  for d in load_disclosures(data_root / "fixtures" / "disclosures")]
        warmed, split = LoopholeStore.load(data_root / "corpus" / "loopholes"), None
        if n is not None:
            graded = graded[:n]  # already id-sorted by the glob
    elif layout == "pooled":
        all_pairs, unpaired = load_pairs(data_root / "disclosures", data_root / "checklists")
        n = DEFAULT_HOLDOUT if n is None else n
        graded, warmed = holdout_split(all_pairs, n, seed)
        if len(warmed) < k:
            # Holding out too much leaves nothing to warm with: both arms would retrieve
            # [] and the resulting zero delta would read as a measured result. Only the
            # pooled layout can do this to itself — the fixtures corpus is a fixed file.
            raise RuntimeError(
                f"holdout n={n} of {len(all_pairs)} leaves a warming corpus of "
                f"{len(warmed)} records, fewer than k={k}"
            )
        split = {
            "seed": seed,
            "n": n,
            "paired": len(all_pairs),
            "holdout_ids": [d.id for d, _ in graded],
            "graded_records": sum(len(c) for _, c in graded),
            "corpus_records": len(warmed),
            "unpaired_disclosure_ids": unpaired,
        }
    else:
        raise ValueError(f"unknown layout {layout!r} — expected 'fixtures' or 'pooled'")

    empty = LoopholeStore.empty()
    if not graded:
        raise RuntimeError(f"no graded disclosures found under {data_root} (layout={layout})")

    out_dir = Path(out_root) / datetime.now().strftime("%Y%m%d-%H%M%S")
    transcript_dir = out_dir / "transcripts"
    transcript_dir.mkdir(parents=True)

    guard_reports = {}
    results: list[EvalResult] = []
    stopped_early = False
    for run_idx in range(runs):
        for disclosure, checklist in graded:
            # Deadline check at the DISCLOSURE boundary keeps every empty/warmed
            # pair complete, and stops the run cold instead of firing calls past
            # the GPU window (which cold-starts a scaled-down endpoint and bills).
            if deadline is not None and time.time() >= deadline:
                stopped_early = True
                break
            if disclosure.id not in guard_reports:
                guard_reports[disclosure.id] = assert_no_overlap(warmed, checklist)
            # paired, back-to-back: empty then warmed on the same disclosure
            for condition, store in (("empty", empty), ("warmed", warmed)):
                results.append(
                    run_condition(disclosure, store, checklist, condition, k, transcript_dir,
                                  run_idx, draft_gen, revise_rounds)
                )
        if stopped_early:
            break

    pairs = _pair_deltas(results)
    payload = {
        "fingerprint": config_fingerprint(k, runs, draft_gen, split, revise_rounds),
        "corpus_size": len(warmed),
        "overlap_guard": guard_reports,
        "results": [r.model_dump() for r in results],
        "pairs": pairs,
        "stopped_early": stopped_early,  # True if the deadline cut the run short
        "disclosures_completed": len(pairs),
    }
    results_path = out_dir / "results.json"
    results_path.write_text(json.dumps(payload, indent=2))
    write_chart(results_path, out_dir / "chart.html")

    latest = Path(out_root) / "latest"
    latest.unlink(missing_ok=True)
    latest.symlink_to(out_dir.resolve())
    return results_path


def _pair_deltas(results: list[EvalResult]) -> list[dict]:
    by_key: dict[tuple, dict] = {}
    for i, r in enumerate(results):
        by_key.setdefault((r.disclosure_id, i // 2), {})[r.condition] = r
    pairs = []
    for (disclosure_id, _), pair in sorted(by_key.items(), key=str):
        if {"empty", "warmed"} <= pair.keys():
            e, w = pair["empty"], pair["warmed"]
            pairs.append(
                {
                    "disclosure_id": disclosure_id,
                    "loopholes_caught_delta": w.loopholes_caught - e.loopholes_caught,
                    "drafting_seconds_delta": round(w.drafting_seconds - e.drafting_seconds, 2),
                    "defect_count_delta": w.defect_count - e.defect_count,
                }
            )
    return pairs
