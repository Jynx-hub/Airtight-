"""Background drafting jobs, so the UI can show the loop instead of a spinner.

A live draft is 3-5 sequential model turns and has been measured at 257s for one
disclosure. `POST /api/draft` blocks for all of it and returns nothing until the
end, which on stage is a multi-minute blank screen over the most interesting
thing this project does.

`draft_patent` already takes a `transcript` list and appends `{turn, messages,
reply}` as each turn lands. Handing it a list we keep a reference to turns that
into a progress feed for free — no change to `agent/loop.py`, whose system
prompts are hashed into every ablation fingerprint.

Polling, not streaming: with reasoning off, the streaming path routes output to
`reasoning_content` and leaves `content` empty (upstream bug in NVIDIA's parser,
see docs/THROUGHPUT.md). Polling sidesteps it entirely.

Scope is one uvicorn process — an in-memory dict, no persistence, no Redis. That
is the right size for a demo and wrong for anything else.
"""

import contextlib
import threading
import time
import uuid
from dataclasses import dataclass, field

from agent.loop import draft_patent
from airtight import Disclosure, Draft, config
from airtight import guardrails as g
from surface import explain, sources

# Keep the last N jobs addressable, then drop the oldest. A demo reloads the page
# more often than it drafts; unbounded growth is the only real leak here.
MAX_JOBS = 50

# The turns the loop always runs. Revise/re-critique are conditional — they fire
# only when the critique names a material defect — so they're appended as they
# appear rather than pre-declared and left perpetually pending.
BASE_STAGES = [
    ("plan", "Plan", "Decompose the disclosure into drafting steps"),
    ("draft", "Draft", "Write claims + specification against the retrieved guardrails"),
    ("critique", "Critique", "Attack the draft as a hostile examiner"),
]

_STAGE_LABELS = {
    "plan": ("Plan", "Decompose the disclosure into drafting steps"),
    "draft": ("Draft", "Write claims + specification against the retrieved guardrails"),
    "critique": ("Critique", "Attack the draft as a hostile examiner"),
}


def _label(turn: str) -> tuple[str, str]:
    if turn in _STAGE_LABELS:
        return _STAGE_LABELS[turn]
    if turn.startswith("revise-"):
        return (f"Revise {turn.split('-')[1]}", "Apply every material defect the examiner named")
    if turn.startswith("critique-"):
        return (f"Re-critique {turn.split('-')[1]}", "Re-attack the revised draft")
    return (turn, "")


@dataclass
class Job:
    id: str
    disclosure: Disclosure
    status: str = "retrieving"  # retrieving | queued | drafting | done | error
    retrieval: dict | None = None
    transcript: list = field(default_factory=list)  # mutated live by draft_patent
    draft: Draft | None = None
    findings: list = field(default_factory=list)  # captured under the draft lock
    error: str | None = None
    started: float = field(default_factory=time.monotonic)
    finished: float | None = None
    # Where this job's entries begin in the process-global AUDIT_LOG. Without it
    # every request re-reports every earlier request's findings — g.AUDIT_LOG is
    # never cleared, so the bug compounds across a demo session.
    audit_offset: int = 0


_JOBS: dict[str, Job] = {}
_LOCK = threading.Lock()

# Only one draft at a time, process-wide.
#
# `audit_offset` is an index into g.AUDIT_LOG, which is a process-global list
# every hop appends to. Slicing from an offset attributes findings correctly
# only if nothing else appended in between — true for sequential requests, false
# the moment two drafts overlap (two tabs, or the /#autodraft rehearsal racing a
# click). Interleaved appends would put one disclosure's blocks in another's
# report, which is worse than the bug this offset was introduced to fix: it is
# wrong *and* plausible.
#
# Serializing is the honest fix available from this layer — per-job attribution
# would have to come from the guardrails bus, and that is engine code this lane
# does not touch. It also costs nothing real: drafting is model-bound on one
# pinned endpoint, so concurrent drafts would contend for the same GPU anyway.
_DRAFT_LOCK = threading.Lock()


@contextlib.contextmanager
def exclusive_draft():
    """Hold the draft lock and yield the audit offset valid for its duration.

    Findings must be read *inside* this block — a slice taken after releasing it
    can pick up the next draft's entries.
    """
    with _DRAFT_LOCK:
        yield len(g.AUDIT_LOG)


def _put(job: Job) -> None:
    with _LOCK:
        _JOBS[job.id] = job
        if len(_JOBS) > MAX_JOBS:
            for stale in sorted(_JOBS, key=lambda j: _JOBS[j].started)[: len(_JOBS) - MAX_JOBS]:
                del _JOBS[stale]


def get(job_id: str) -> Job | None:
    with _LOCK:
        return _JOBS.get(job_id)


def security_findings(offset: int) -> list[dict]:
    """Non-pass guardrail events recorded since `offset`.

    Slicing from the offset is what keeps one request's quarantines out of the
    next request's report.
    """
    return [
        {
            "hop": r["hop"],
            "action": r["action"],
            "source": r.get("source"),
            "categories": r.get("categories", []),
            "event_id": r.get("event_id"),
        }
        for r in g.AUDIT_LOG[offset:]
        if r["action"] != "pass"
    ]


def retrieve_for(disclosure: Disclosure, k: int = 5) -> tuple[list, dict]:
    """What memory offers for this disclosure: the records, and why.

    Both come off one merged list and one disk load, so the records handed to the
    drafting turn are provably the ones the panel explained — not a second
    retrieval that could rank differently.
    """
    from agent.memory import _retrieve

    store = sources.retrieval_store()
    merged: dict[str, object] = {}
    # dedup by id, base wins — the same rule CompositeStore.retrieve applies
    for rec in list(store.base.records) + store.episodes._lessons(store.live_only):
        merged.setdefault(rec.id, rec)
    records = list(merged.values())
    return _retrieve(records, disclosure, k), explain.explain_retrieval(records, disclosure, k=k)


def start(disclosure: Disclosure, k: int = 5) -> Job:
    job = Job(id=uuid.uuid4().hex[:12], disclosure=disclosure)
    _put(job)
    threading.Thread(target=_run, args=(job, k), daemon=True).start()
    return job


def _run(job: Job, k: int) -> None:
    try:
        # Retrieval is pure ranking — no model call, no audit entries — so it
        # runs before the lock and a queued job still shows its context match.
        guardrails, job.retrieval = retrieve_for(job.disclosure, k=k)
        job.status = "queued"
        with exclusive_draft() as offset:
            job.audit_offset = offset
            job.status = "drafting"
            # `job.transcript` is handed in by reference — draft_patent appends
            # to it as each turn returns, which is what the poll route reads.
            job.draft = draft_patent(
                job.disclosure, guardrails=guardrails, transcript=job.transcript)
            job.findings = security_findings(offset)  # inside the lock, by contract
        job.status = "done"
    except Exception as exc:
        job.error = f"{type(exc).__name__}: {exc}"
        job.status = "error"
    finally:
        job.finished = time.monotonic()


def snapshot(job: Job) -> dict:
    """The poll payload: everything known about the job right now."""
    stages = []
    seen = set()
    for entry in list(job.transcript):  # copy — the worker thread may append mid-read
        turn = entry.get("turn", "")
        seen.add(turn)
        label, detail = _label(turn)
        stages.append({
            "turn": turn,
            "label": label,
            "detail": detail,
            "state": "done",
            "reply": entry.get("reply", ""),
            "system": next((m["content"] for m in entry.get("messages", [])
                            if m.get("role") == "system"), ""),
        })

    # Show the turns that haven't landed yet as pending, so the pipeline reads as
    # a plan being executed rather than a list that grows out of nowhere.
    if job.status in ("retrieving", "queued", "drafting"):
        for turn, label, detail in BASE_STAGES:
            if turn not in seen:
                stages.append({"turn": turn, "label": label, "detail": detail,
                               "state": "running" if turn == _next_turn(seen) else "pending",
                               "reply": "", "system": ""})

    elapsed = (job.finished or time.monotonic()) - job.started
    return {
        "job_id": job.id,
        "status": job.status,
        "elapsed_s": round(elapsed, 2),
        "mode": config.MODE,
        "retrieval": job.retrieval,
        "stages": stages,
        "error": job.error,
        "draft": job.draft.model_dump() if job.draft else None,
        "report": _report(job) if job.draft else None,
    }


def _next_turn(seen: set) -> str:
    for turn, _, _ in BASE_STAGES:
        if turn not in seen:
            return turn
    return ""


def _report(job: Job) -> dict:
    draft = job.draft
    return {
        "smart_catches": draft.critique_notes,
        "loopholes_closed": draft.loopholes_closed,
        # Captured under the draft lock, not re-sliced here: by the time a poll
        # arrives, the next draft may already have appended to AUDIT_LOG.
        "security_findings": job.findings,
        "security_scanning": config.HL_ENABLED,
        # How many retrieved records the drafting turn was actually primed with.
        # `loopholes_closed` is the ids passed in, not a claim that each was cured
        # — the judge in agent/eval/judge.py is what verifies closure, and it does
        # not run on this path.
        "guardrails_applied": len(draft.loopholes_closed),
        "verified": False,
    }
