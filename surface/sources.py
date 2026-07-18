"""Read-only views over what the engine has already written to disk.

Everything the admin frame shows comes from here. Two rules hold throughout:

*Nothing raises.* A panel whose data is missing, half-written or from an older
schema renders a labelled seam instead of a 500. This is not defensive
paranoia — all three states exist in `results/ablation/` right now: a complete
run, a run predating the revise turn, and one killed mid-flight that has
transcripts and no `results.json`.

*Nothing is claimed that isn't true.* Readers attach the caveat alongside the
number (superseded corpus, simulated enforcement, absent knee) rather than
leaving the frontend to remember it. `docs/WORKSTREAMS.md` is the source for
which claims carry which caveat.
"""

import json
import pathlib
import re
from collections import Counter

from airtight import config

ROOT = pathlib.Path(__file__).resolve().parent.parent

ABLATION_DIR = ROOT / "results" / "ablation"
SECURITY_DIR = ROOT / "results" / "security"
BENCH_DIR = ROOT / "runtime" / "bench-results"
CORPUS_DIR = ROOT / "data" / "real" / "groundtruth"
POLICY_PATH = ROOT / "inference" / "policy" / "airtight-sandbox.yaml"

# The five hops in the order the bus sees them, so an empty hop still gets a row
# rather than vanishing from the chart. Mirrors airtight.guardrails.Hop.
HOPS = ["user_prompt", "model_response", "tool_call", "tool_result", "ingested_document"]
ACTIONS = ["pass", "redact", "quarantine", "block"]


def seam(label: str, detail: str, source: str) -> dict:
    """A placeholder that names its own future. `source` is the exact path or
    command that fills it, so wiring it up later is a lookup, not a hunt."""
    return {"seam": True, "label": label, "detail": detail, "source": source}


def _read_json(path: pathlib.Path):
    try:
        return json.loads(path.read_text())
    except (OSError, ValueError):
        return None


def _read_jsonl(path: pathlib.Path) -> list[dict]:
    if not path.exists():
        return []
    rows = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except ValueError:
            continue  # a torn last line mid-write shouldn't lose the other 200
    return rows


# --------------------------------------------------------------------------
# Ablation — the M4 empty-vs-warmed result
# --------------------------------------------------------------------------

def ablation_runs() -> dict:
    """Every run dir, newest first, each tagged with whether it can be charted.

    Fingerprint keys are read with .get() throughout: `revise_rounds`, `split`
    and the REVISE_SYSTEM prompt hash postdate the older run, and reading them
    positionally is how this 500s.
    """
    if not ABLATION_DIR.exists():
        return {"runs": [], "selected": None, "seam": seam(
            "NO RUNS ON DISK",
            "The ablation has not been run in this clone.",
            "python -m agent.eval --layout pooled --data-root data/real",
        )}

    runs = []
    for d in sorted(ABLATION_DIR.iterdir(), reverse=True):
        if not d.is_dir():
            continue
        data = _read_json(d / "results.json")
        transcripts = sorted((d / "transcripts").glob("*.json")) if (d / "transcripts").exists() else []
        if data is None:
            # Killed mid-run: transcripts exist, the file the chart needs doesn't.
            runs.append({
                "id": d.name,
                "complete": False,
                "transcript_count": len(transcripts),
                "seam": seam(
                    "INCOMPLETE RUN",
                    f"{len(transcripts)} transcripts written, no results.json — the run was killed "
                    "before it aggregated.",
                    f"results/ablation/{d.name}/",
                ),
            })
            continue

        fp = data.get("fingerprint", {})
        runs.append({
            "id": d.name,
            "complete": True,
            "transcript_count": len(transcripts),
            "corpus_size": data.get("corpus_size"),
            "disclosures_completed": data.get("disclosures_completed"),
            "stopped_early": data.get("stopped_early", False),
            "results": data.get("results", []),
            "pairs": data.get("pairs", []),
            "totals": _ablation_totals(data.get("results", [])),
            "fingerprint": {
                "timestamp": fp.get("timestamp"),
                "mode": fp.get("mode"),
                "model": fp.get("model"),
                "git_sha": fp.get("git_sha"),
                "k": fp.get("k"),
                "runs": fp.get("runs"),
                # Absent on runs predating the revise turn — the frontend renders
                # "—" rather than implying 0 rounds were configured.
                "revise_rounds": fp.get("revise_rounds"),
                "base_url_host": fp.get("base_url_host"),
                "has_revise_prompt": "REVISE_SYSTEM" in fp.get("prompt_sha256", {}),
            },
        })

    selected = next((r for r in runs if r["complete"]), None)
    return {
        "runs": runs,
        "selected": selected,
        # The caveat travels with the data. WORKSTREAMS: the corpus that produced
        # these numbers is gone from the tree and retrieval has changed twice since.
        "caveat": seam(
            "SUPERSEDED RUN",
            "Warmed on a corpus (data/real-eval/) no longer in the tree, and retrieval has been "
            "rewritten twice since (C1 statute diversification, C2 BM25 b=0.3). Directionally real, "
            "not currently reproducible — do not quote until the GPU re-run lands.",
            "docs/WORKSTREAMS.md · results/ablation/",
        ),
    }


def _ablation_totals(results: list[dict]) -> dict:
    """Aggregate each arm. Time is summed but flagged: the empty arm's total is
    dominated by one 257s outlier, which WORKSTREAMS rules out as a claim."""
    out = {}
    for cond in ("empty", "warmed"):
        rows = [r for r in results if r.get("condition") == cond]
        out[cond] = {
            "caught": sum(r.get("loopholes_caught", 0) for r in rows),
            "checklist": sum(r.get("checklist_size", 0) for r in rows),
            "defects": sum(r.get("defect_count", 0) for r in rows),
            "seconds": round(sum(r.get("drafting_seconds", 0.0) for r in rows), 2),
            "n": len(rows),
        }
    return out


# --------------------------------------------------------------------------
# Security bus — the HiddenLayer hop log
# --------------------------------------------------------------------------

# A real AIDR event_id is a UUID (research/hiddenlayer.md §5). Everything else in
# this log is synthetic: "fake-*" from the ingest rehearsal fixtures, "evt-test"
# and "e" from the test suite. That distinction matters more than it looks —
# guardrails._persist() writes unconditionally, so `pytest` appends to the very
# same audit.jsonl the demo reads. Counting them together would put 77 test-suite
# blocks on screen as if the agent had been stopped 77 times.
_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)


def _is_live(row: dict) -> bool:
    return bool(_UUID_RE.match(str(row.get("event_id") or "")))


def security_events(tail: int = 40) -> dict:
    """Hop x action counts plus the recent tail, from the three JSONL logs.

    audit.jsonl is every analyzed hop; quarantine/escalations are the subsets
    that tripped. Counting only audit.jsonl keeps the matrix a true census —
    the other two would double-count the same events.

    Every count is split live vs synthetic. The panel shows both and says which
    is which; the alternative is a security dashboard whose headline number is
    mostly `pytest`.
    """
    audit = _read_jsonl(SECURITY_DIR / "audit.jsonl")
    quarantine = _read_jsonl(SECURITY_DIR / "quarantine.jsonl")
    escalations = _read_jsonl(SECURITY_DIR / "escalations.jsonl")

    live = [r for r in audit if _is_live(r)]
    synthetic = [r for r in audit if not _is_live(r)]

    def matrix_of(rows: list[dict]) -> dict:
        m = {hop: {a: 0 for a in ACTIONS} for hop in HOPS}
        for row in rows:
            hop, action = row.get("hop"), row.get("action")
            if hop in m and action in m[hop]:
                m[hop][action] += 1
        return m

    return {
        "enabled": config.HL_ENABLED,
        "matrix": matrix_of(audit),
        "matrix_live": matrix_of(live),
        "hops": HOPS,
        "actions": ACTIONS,
        "counts": {
            "audit": len(audit),
            "quarantine": len(quarantine),
            "escalations": len(escalations),
            "live": len(live),
            "synthetic": len(synthetic),
        },
        "by_action": dict(Counter(r.get("action") for r in audit)),
        "by_category": dict(Counter(c for r in audit for c in r.get("categories", []))),
        "events": [
            {**r, "live": _is_live(r)}
            for r in sorted(audit, key=lambda r: r.get("ts", ""), reverse=True)[:tail]
        ],
        # A real AIDR event_id is the difference between "we called the API" and
        # "we say we called the API". Surface the sample so the panel can prove it.
        "sample_live_event_id": live[0].get("event_id") if live else None,
        "provenance_seam": seam(
            "NO LIVE EVENTS" if not live else "MIXED PROVENANCE",
            f"{len(live)} of {len(audit)} audited hops carry a real AIDR event_id (UUID). The rest are "
            "fixtures — ingest rehearsal (fake-*) and test-suite writes (evt-test, e). "
            "guardrails._persist() writes unconditionally, so running pytest appends to this log. "
            "A live run was verified 2026-07-18 but its rows are not in this (gitignored) log.",
            "AIRTIGHT_HL_ENABLED=true python -m agent.poison_demo   # drop --fake; key expires in 24h",
        ) if synthetic else None,
    }


# --------------------------------------------------------------------------
# Throughput — the vLLM batching sweeps
# --------------------------------------------------------------------------

def throughput_sweeps() -> dict:
    """Every bench sweep, newest first. Provenance rides along because the two
    GPU profiles tell different stories and the knee claim belongs to only one."""
    if not BENCH_DIR.exists():
        return {"sweeps": [], "selected": None, "seam": seam(
            "NO SWEEPS ON DISK",
            "No benchmark has been run in this clone.",
            "python runtime/bench.py",
        )}

    sweeps = []
    for path in sorted(BENCH_DIR.glob("sweep-*.json"), reverse=True):
        data = _read_json(path)
        if data is None:
            continue
        prov, summary = data.get("provenance", {}), data.get("summary", {})
        sweeps.append({
            "id": path.stem,
            "captured_utc": prov.get("captured_utc"),
            "gpu": prov.get("gpu_reported_by_operator"),
            "notes": prov.get("notes"),
            "max_num_seqs": prov.get("max_num_seqs_deployed"),
            "levels": data.get("levels", []),
            "summary": summary,
            # knee_concurrency is null on the L40S profile — C=32 still adds
            # +16.6% there, so the "plateaus at the pinned max-num-seqs" story is
            # an A100 result. Pass the null through; don't invent a knee.
            "has_knee": summary.get("knee_concurrency") is not None,
        })

    # Default to the quotable headline: of the runs that actually kneed, the
    # strongest. THROUGHPUT.md is explicit that the knee claim belongs to the
    # A100 profile only, so a sweep without one must never be the default view.
    kneed = [s for s in sweeps if s["has_knee"]]
    selected = (max(kneed, key=lambda s: s["summary"].get("headline_speedup_x", 0))
                if kneed else (sweeps[0] if sweeps else None))
    return {"sweeps": sweeps, "selected": selected}


# --------------------------------------------------------------------------
# Memory — corpus, episodes, ingested
# --------------------------------------------------------------------------

def _load_store(directory: pathlib.Path):
    """LoopholeStore.load, but tolerant of a missing dir.

    Loading through the store (not json.load) is mandatory: `statute` and
    `extraction_confidence` are absent from every on-disk record and are derived
    by a model_validator. Read the files raw and the whole corpus shows a blank
    statute.
    """
    from agent.memory import LoopholeStore

    if not directory.exists():
        return LoopholeStore([], None)
    try:
        return LoopholeStore.load(directory)
    except (OSError, ValueError):
        return LoopholeStore([], None)


def corpus_store():
    """Ground truth + anything distilled from ingested documents, id-deduped."""
    from agent.memory import merged_store

    return merged_store(_load_store(CORPUS_DIR), _load_store(ROOT / config.INGESTED_DIR))


def episode_store():
    from agent.episodes import EpisodeStore

    directory = ROOT / config.EPISODES_DIR
    if not directory.exists():
        return EpisodeStore([], None)
    try:
        return EpisodeStore.load(directory)
    except (OSError, ValueError):
        return EpisodeStore([], None)


def retrieval_store():
    """The store the intake frame actually retrieves against — corpus plus
    whatever the agent has taught itself, behind one retrieve()."""
    from agent.episodes import CompositeStore

    return CompositeStore(corpus_store(), episode_store())


def memory_stats() -> dict:
    ground = _load_store(CORPUS_DIR)
    ingested = _load_store(ROOT / config.INGESTED_DIR)
    episodes = episode_store()
    lessons = [rec for ep in episodes.episodes for rec in ep.distilled]

    return {
        "corpus": {
            "count": len(ground),
            "by_statute": dict(Counter(r.statute or "?" for r in ground.records)),
            "by_class": dict(Counter(r.technology_class for r in ground.records)),
            "source": "data/real/groundtruth/loopholes.json",
        },
        "ingested": {
            "count": len(ingested),
            "by_statute": dict(Counter(r.statute or "?" for r in ingested.records)),
            "seam": None if len(ingested) else seam(
                "NOT POPULATED",
                "No document has been ingested into memory yet. Records land here at "
                "confidence 0.3 and compete on rank alone — they never take a reserved statute slot.",
                "python -m agent.ingest <path> --remember --tech-class G06F",
            ),
        },
        "episodes": {
            "count": len(episodes),
            "lessons": len(lessons),
            "enabled": config.EPISODES_ENABLED,
            "seam": None if len(episodes) else seam(
                "NOT POPULATED",
                "The loop compounds by distilling its own critique into lessons at confidence 0.5. "
                f"Writes are opt-in and env-gated (currently {'on' if config.EPISODES_ENABLED else 'off'}); "
                "the ablation harness never passes a sink, so this can never contaminate a judged run.",
                "memory/episodes/<disclosure_id>/ · AIRTIGHT_EPISODES_ENABLED=1",
            ),
        },
    }


def disclosures(limit: int = 200) -> dict:
    """The real pulled disclosures, for the retrieval inspector to aim at.

    Summary only — `details` is the full claim listing and runs past 10 KB on
    some records, which is a lot of bytes to ship for a dropdown.
    """
    directory = ROOT / "data" / "real" / "disclosures"
    if not directory.exists():
        return {"disclosures": [], "total": 0, "seam": seam(
            "NO CORPUS PULLED",
            "No disclosures in this clone.",
            "python data/pull_uspto.py --groundtruth --cpc G06 --limit 50",
        )}

    items = []
    for path in sorted(directory.glob("*.json"))[:limit]:
        data = _read_json(path)
        if data:
            items.append({
                "id": data.get("id"),
                "title": data.get("title", "")[:120],
                "technology_class": data.get("technology_class"),
            })
    return {"disclosures": items, "total": len(list(directory.glob("*.json")))}


def disclosure(disclosure_id: str):
    """Full record by id, for the inspector to actually retrieve against."""
    from airtight import Disclosure

    path = ROOT / "data" / "real" / "disclosures" / f"{disclosure_id}.json"
    if not path.exists():
        return None
    try:
        return Disclosure.model_validate_json(path.read_text())
    except (OSError, ValueError):
        return None


def memory_records(statute: str = "", cpc: str = "", q: str = "", limit: int = 50) -> dict:
    """Faceted browse over the retrievable corpus."""
    records = corpus_store().records
    if statute:
        records = [r for r in records if (r.statute or "?") == statute]
    if cpc:
        records = [r for r in records if r.technology_class == cpc]
    if q:
        needle = q.lower()
        records = [r for r in records
                   if needle in r.pattern.lower() or needle in r.claim_shape.lower()]

    total = len(records)
    return {
        "total": total,
        "shown": min(total, limit),
        "records": [
            {
                "id": r.id,
                "statute": r.statute,
                "pattern": r.pattern,
                "claim_shape": r.claim_shape,
                "remedy": r.remedy,
                "technology_class": r.technology_class,
                "source": r.source,
                "confidence": r.extraction_confidence,
            }
            for r in records[:limit]
        ],
    }


# --------------------------------------------------------------------------
# Containment — the OpenShell policy, as written
# --------------------------------------------------------------------------

# Static tiers are locked at sandbox creation; dynamic ones hot-reload. The split
# is the point: the inference tier is dynamic, which is what lets the operator
# pin the model hop without rebuilding the sandbox.
TIERS = [
    {"tier": "filesystem", "mutability": "static",
     "boundary": "read-only /usr /etc /bin /lib; writable only under /sandbox and /tmp"},
    {"tier": "process", "mutability": "static",
     "boundary": "runs as non-root user `agent`; no privilege escalation"},
    {"tier": "network", "mutability": "dynamic",
     "boundary": "per-binary egress allow-list; patent sources GET-only; filing POST hard-denied"},
    {"tier": "inference", "mutability": "dynamic",
     "boundary": "pinned to inference.local — the agent cannot choose its own model endpoint"},
]


def containment_policy() -> dict:
    """The four tiers plus the network rules, parsed from the real YAML.

    Decisions in `containment/policy.py` are driven by this file, so what's shown
    here is what would actually be enforced — if anything enforced. It doesn't:
    the enforcement path is a print(), which is why this carries a seam.
    """
    policy, error = None, None
    try:
        import yaml

        policy = yaml.safe_load(POLICY_PATH.read_text())
    except (OSError, ValueError, ImportError) as exc:
        error = str(exc)

    endpoints = []
    for name, block in (policy or {}).get("network_policies", {}).items():
        for ep in block.get("endpoints", []):
            endpoints.append({
                "policy": name,
                "host": ep.get("host"),
                "enforcement": ep.get("enforcement"),
                "access": ep.get("access"),
                "allow": [f"{r['allow']['method']} {r['allow']['path']}"
                          for r in ep.get("rules", []) if "allow" in r],
                "deny": [f"{r['method']} {r['path']}" for r in ep.get("deny_rules", [])],
            })

    return {
        "tiers": TIERS,
        "endpoints": endpoints,
        "error": error,
        "decisions": ["allow", "default_deny_escalate", "hard_deny"],
        "enforcement_seam": seam(
            "SIMULATED",
            "Policy decisions are real and driven by this YAML — editing a deny_rule changes the "
            "outcome. Enforcement is not: containment/openshell_sim.py prints what OpenShell would "
            "do. Landlock and seccomp need a Linux host. Do not imply live enforcement on stage.",
            "containment/openshell_sim.py · docs/WORKSTREAMS.md lane A",
        ),
        "gateway_seam": seam(
            "NAMING CONTRACT ONLY",
            "inference.local has no DNS entry and no gateway process. The invariant it protects — the "
            "agent cannot pick its own endpoint — is enforced today in code; the hostname and "
            "host-side credential injection close at F5.",
            "docs/INFERENCE-LOCAL.md",
        ),
    }
