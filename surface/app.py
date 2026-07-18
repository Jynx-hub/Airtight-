"""Applicant Surface backend (Person 3's lane, D1/D5).

Thin on purpose — the engine is the star. Exposes the JSON contract the two
frames consume and serves them. Calls only agent.loop.draft_patent, so the
doorway / HiddenLayer invariant holds (no raw model access here).

Two frames:
  /        the intake console — disclosure in, retrieved context, live pipeline, grant
  /admin   the engine panel — retrieval, ablation, security bus, throughput, containment

Read-side logic lives in surface/sources.py (disk) and surface/explain.py
(retrieval reasoning); drafting lives in surface/jobs.py. This file is routing.

    pip install -e ".[web]"
    uvicorn surface.app:app --reload      # then open http://localhost:8000
"""

import pathlib

from fastapi import FastAPI, HTTPException
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from agent.loop import draft_patent
from airtight import Disclosure, Draft, config
from surface import jobs, sources

STATIC = pathlib.Path(__file__).resolve().parent / "static"
SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_disclosure.json"

app = FastAPI(title="Airtight — Applicant Surface")

# Needed for split CSS/JS. `/` and `/admin` still hand-serve their HTML so the
# page URLs stay clean.
app.mount("/static", StaticFiles(directory=STATIC), name="static")


class SecurityFinding(BaseModel):
    hop: str
    action: str
    source: str | None = None
    categories: list[str] = []
    event_id: str | None = None  # real AIDR ids are UUIDs; fixtures aren't


class LoopholeReport(BaseModel):
    """The grant attachment — smart-catches (from drafting) + security findings
    (from Person 2's HiddenLayer bus). Honest: security is empty when HL is off."""

    smart_catches: list[str]  # critique notes the agent raised against its own draft
    loopholes_closed: list[str]  # loophole ids the retrieved memory pre-empted
    security_findings: list[SecurityFinding]  # quarantines/blocks from the guardrails bus
    security_scanning: bool  # False in stub / HL-off mode — no findings expected


class DraftResponse(BaseModel):
    draft: Draft
    report: LoopholeReport


# ---------------------------------------------------------------------------
# Pages
# ---------------------------------------------------------------------------

@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/admin")
def admin() -> FileResponse:
    return FileResponse(STATIC / "admin.html")


@app.get("/api/health")
def health() -> dict:
    return {"mode": config.MODE, "model": config.MODEL, "hl_enabled": config.HL_ENABLED}


@app.get("/api/sample")
def sample() -> Disclosure:
    return Disclosure.model_validate_json(SAMPLE.read_text())


# ---------------------------------------------------------------------------
# Drafting
# ---------------------------------------------------------------------------

@app.post("/api/draft")
def draft(disclosure: Disclosure) -> DraftResponse:
    """Synchronous draft. Kept for scripted/CLI use; the UI uses the job routes.

    Retrieval is applied here too. Without it `render_guardrails([])` renders
    "(none on record)" and `loopholes_closed` is always empty — i.e. the
    synchronous path silently ran the ablation's *control* arm and reported it as
    the product.
    """
    guardrails, _ = jobs.retrieve_for(disclosure)
    # Serialized, and the findings slice is taken inside the lock — otherwise a
    # concurrent draft's blocks land in this request's report. See jobs.py.
    with jobs.exclusive_draft() as offset:
        result = draft_patent(disclosure, guardrails=guardrails)
        findings = [SecurityFinding(**f) for f in jobs.security_findings(offset)]
    report = LoopholeReport(
        smart_catches=result.critique_notes,
        loopholes_closed=result.loopholes_closed,
        security_findings=findings,
        security_scanning=config.HL_ENABLED,
    )
    return DraftResponse(draft=result, report=report)


@app.post("/api/draft/start")
def draft_start(disclosure: Disclosure, k: int = 5) -> dict:
    """Kick off a draft in the background; poll /api/draft/{job_id} for progress."""
    job = jobs.start(disclosure, k=k)
    return {"job_id": job.id, "status": job.status}


@app.get("/api/draft/{job_id}")
def draft_status(job_id: str) -> dict:
    job = jobs.get(job_id)
    if job is None:
        raise HTTPException(status_code=404, detail="unknown job")
    return jobs.snapshot(job)


# ---------------------------------------------------------------------------
# Engine views (admin frame) — all read-only
# ---------------------------------------------------------------------------

@app.get("/api/memory/stats")
def memory_stats() -> dict:
    return sources.memory_stats()


@app.get("/api/memory/records")
def memory_records(statute: str = "", cpc: str = "", q: str = "", limit: int = 50) -> dict:
    return sources.memory_records(statute=statute, cpc=cpc, q=q, limit=min(limit, 200))


@app.get("/api/disclosures")
def disclosures(limit: int = 200) -> dict:
    return sources.disclosures(limit=min(limit, 500))


@app.post("/api/memory/retrieve")
def memory_retrieve(disclosure: Disclosure, k: int = 5) -> dict:
    """Dry-run retrieval: what would prime the drafting turn, and why. No model call."""
    _, payload = jobs.retrieve_for(disclosure, k=k)
    return payload


@app.get("/api/memory/retrieve/{disclosure_id}")
def memory_retrieve_by_id(disclosure_id: str, k: int = 5) -> dict:
    """Same, against a disclosure already in the corpus."""
    disc = sources.disclosure(disclosure_id)
    if disc is None:
        raise HTTPException(status_code=404, detail="unknown disclosure")
    _, payload = jobs.retrieve_for(disc, k=k)
    return payload


@app.get("/api/ablation")
def ablation() -> dict:
    return sources.ablation_runs()


@app.get("/api/security")
def security() -> dict:
    return sources.security_events()


@app.get("/api/throughput")
def throughput() -> dict:
    return sources.throughput_sweeps()


@app.get("/api/containment")
def containment() -> dict:
    return sources.containment_policy()
