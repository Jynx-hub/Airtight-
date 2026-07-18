"""Applicant Surface backend (Person 3's lane, D1).

Thin on purpose — the engine is the star. Exposes the JSON contract a frontend
consumes (a later Next.js app or the shipped HTML page) and serves the page.
Calls only agent.loop.draft_patent, so the doorway / HiddenLayer invariant holds
(no raw model access here).

    uvicorn surface.app:app --reload      # then open http://localhost:8000
"""

import pathlib

from fastapi import FastAPI
from fastapi.responses import FileResponse
from pydantic import BaseModel

from airtight import Disclosure, Draft, config
from airtight import guardrails as g
from agent.loop import draft_patent

STATIC = pathlib.Path(__file__).resolve().parent / "static"
SAMPLE = pathlib.Path(__file__).resolve().parent.parent / "data" / "fixtures" / "sample_disclosure.json"

app = FastAPI(title="Airtight — Applicant Surface")


class SecurityFinding(BaseModel):
    hop: str
    action: str
    source: str | None = None
    categories: list[str] = []


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


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC / "index.html")


@app.get("/api/health")
def health() -> dict:
    return {"mode": config.MODE, "model": config.MODEL, "hl_enabled": config.HL_ENABLED}


@app.get("/api/sample")
def sample() -> Disclosure:
    return Disclosure.model_validate_json(SAMPLE.read_text())


@app.post("/api/draft")
def draft(disclosure: Disclosure) -> DraftResponse:
    result = draft_patent(disclosure)
    findings = [
        SecurityFinding(
            hop=r["hop"], action=r["action"], source=r.get("source"), categories=r.get("categories", [])
        )
        for r in g.AUDIT_LOG
        if r["action"] != "pass"
    ]
    report = LoopholeReport(
        smart_catches=result.critique_notes,
        loopholes_closed=result.loopholes_closed,
        security_findings=findings,
        security_scanning=config.HL_ENABLED,
    )
    return DraftResponse(draft=result, report=report)
