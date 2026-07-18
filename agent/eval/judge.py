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
DEFECT_GEN = {**JUDGE_GEN, "max_tokens": 600}  # bound the list so it can't ramble
DEFECT_CAP = 6  # backstop on hallucinated over-listing

CHECKLIST_SYSTEM = (
    "You are a patent examiner scoring one draft against one known loophole. The "
    "loophole is CLOSED only if specific claim language forecloses the "
    "design-around — merely mentioning the topic is not enough. Reply with JSON "
    'only: {"closed": true|false, "evidence": "<verbatim quote of the closing '
    'claim language, or null>"}'
)

DEFECT_SYSTEM = (
    "You are a strict USPTO examiner reviewing patent claims. List ONLY material, "
    "clearly-supported defects under exactly these grounds: 112 (indefiniteness, "
    "antecedent-basis, enablement); 102 (facial anticipation); 103 (facial "
    "obviousness). Rules: (1) `quote` MUST be exact verbatim language copied from "
    "the CLAIMS — never paraphrase, never quote the specification; (2) one entry "
    "per distinct defect, no duplicates; (3) at most 6 defects, most serious "
    "first; (4) do NOT pad — a well-drafted claim set may have zero or one. Reply "
    'with JSON only: {"defects": [{"section": "112"|"102"|"103", "claim": <int>, '
    '"type": "<short label>", "quote": "<verbatim claim language>"}]}. '
    'No material defect => {"defects": []}.'
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
    """Return only defects whose verbatim `quote` actually appears in the claims,
    deduplicated and capped — so a hallucinated over-list can't inflate the count.
    Same evidence discipline that makes score_checklist trustworthy."""
    reply = call_model(
        [
            {"role": "system", "content": DEFECT_SYSTEM},
            {"role": "user", "content": f"CLAIMS\n{claims_text}\n\nSPECIFICATION\n{spec_text}"},
        ],
        role="tool",
        **DEFECT_GEN,
    )
    if reply.mode == "stub":
        return []

    claims_norm = _norm(claims_text)
    data = _parse_json(reply.text) or {}
    defects, seen = [], set()
    for raw in data.get("defects", []):
        if not isinstance(raw, dict):
            continue
        try:
            defect = Defect.model_validate({**raw, "section": str(raw.get("section", ""))})
        except Exception:
            continue  # malformed entries dropped, never guessed
        quote = _norm(defect.quote)
        if not quote or quote not in claims_norm:
            continue  # ungrounded / hallucinated quote — drop it
        key = (defect.section, quote)
        if key in seen:
            continue  # duplicate
        seen.add(key)
        defects.append(defect)
        if len(defects) >= DEFECT_CAP:
            break
    return defects
