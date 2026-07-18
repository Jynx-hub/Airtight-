"""Blinded LLM judge for the M4 ablation.

The judge never sees the condition label, the guardrails, or the other draft —
only draft text plus one checklist item at a time. closed=true requires a
verbatim evidence quote that actually appears in the claims; unverifiable
evidence is downgraded to not-closed. In stub mode the judge returns
closed=False / no defects — it never fabricates a delta.
"""

import json
import re
from typing import Literal, Optional

from pydantic import BaseModel

from airtight import LoopholeRecord, call_model

JUDGE_GEN = {"temperature": 0.0, "seed": 1234}

CHECKLIST_SYSTEM = (
    "You are a patent examiner scoring one draft against one known loophole. The "
    "loophole is CLOSED only if specific claim language forecloses the "
    "design-around — merely mentioning the topic is not enough. Reply with JSON "
    'only: {"closed": true|false, "evidence": "<verbatim quote of the closing '
    'claim language, or null>"}'
)

DEFECT_SYSTEM = (
    "You are a USPTO examiner. Identify defects in the claims and specification "
    "below under exactly these grounds: 112 indefiniteness (including "
    "antecedent-basis errors) and enablement/written-description gaps; 102 facial "
    "anticipation risk; 103 facial obviousness risk. List each defect once. Reply "
    'with JSON only: {"defects": [{"section": "112"|"102"|"103", "claim": <int>, '
    '"type": "<short label>", "quote": "<offending language>"}]}. '
    'No defects => {"defects": []}.'
)


class ChecklistVerdict(BaseModel):
    item_id: str
    closed: bool
    evidence: Optional[str] = None
    judge_mode: str  # "live" | "stub"


class Defect(BaseModel):
    section: Literal["112", "102", "103"]
    claim: int
    type: str
    quote: str


def _norm(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip().lower()


def _parse_json(text: str) -> dict | None:
    match = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not match:
        return None
    try:
        return json.loads(match.group(0))
    except json.JSONDecodeError:
        return None


def score_checklist(claims_text: str, checklist: list[LoopholeRecord]) -> list[ChecklistVerdict]:
    verdicts = []
    for item in checklist:
        user = (
            f"LOOPHOLE\npattern: {item.pattern}\n"
            f"claim shape that triggered it: {item.claim_shape}\n"
            f"remedy that fixed it: {item.remedy}\n\n"
            f"DRAFT CLAIMS\n{claims_text}"
        )
        reply = call_model(
            [{"role": "system", "content": CHECKLIST_SYSTEM}, {"role": "user", "content": user}],
            role="tool",
            **JUDGE_GEN,
        )
        if reply.mode == "stub":
            verdicts.append(ChecklistVerdict(item_id=item.id, closed=False, judge_mode="stub"))
            continue

        data = _parse_json(reply.text) or {}
        closed = bool(data.get("closed"))
        evidence = data.get("evidence")
        if closed and not (isinstance(evidence, str) and _norm(evidence) in _norm(claims_text)):
            closed, evidence = False, None  # unverifiable evidence => not closed
        verdicts.append(
            ChecklistVerdict(item_id=item.id, closed=closed, evidence=evidence, judge_mode="live")
        )
    return verdicts


def count_defects(claims_text: str, spec_text: str) -> list[Defect]:
    reply = call_model(
        [
            {"role": "system", "content": DEFECT_SYSTEM},
            {"role": "user", "content": f"CLAIMS\n{claims_text}\n\nSPECIFICATION\n{spec_text}"},
        ],
        role="tool",
        **JUDGE_GEN,
    )
    if reply.mode == "stub":
        return []

    data = _parse_json(reply.text) or {}
    defects = []
    for raw in data.get("defects", []):
        if isinstance(raw, dict):
            raw = {**raw, "section": str(raw.get("section", ""))}
        try:
            defects.append(Defect.model_validate(raw))
        except Exception:
            continue  # malformed entries are dropped, never guessed
    return defects
