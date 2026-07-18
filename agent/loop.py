"""The M1 work loop: plan → draft → self-critique → assemble.

Plain Python on purpose — LangChain Deep Agents is an M3 option, not a day-one
dependency. Every model turn goes through the doorway; nothing else in this
repo may talk to a model.
"""

import re

from airtight import Disclosure, Draft, call_model

PLAN_SYSTEM = (
    "You are the planning module of a patent-drafting agent. Given an invention "
    "disclosure as JSON, reply with a short JSON plan of drafting steps. Reply "
    "with JSON only."
)

DRAFT_SYSTEM = (
    "You are a patent attorney. Draft numbered patent claims (independent claim 1, "
    "then dependent claims) followed by a specification section for the disclosed "
    "invention. Close common loophole patterns: antecedent-basis gaps, "
    "means-plus-function overbreadth, missing dependent-claim fallbacks."
)

CRITIQUE_SYSTEM = (
    "You are a hostile patent examiner. Attack the draft below: find §112 "
    "indefiniteness, antecedent-basis errors, §102/§103 exposure, and claim "
    "language a competitor could design around. Reply as a bulleted list of "
    "defects, most severe first."
)


def draft_patent(disclosure: Disclosure) -> Draft:
    plan = call_model(
        [
            {"role": "system", "content": PLAN_SYSTEM},
            {"role": "user", "content": disclosure.model_dump_json()},
        ],
        role="tool",
    )

    draft = call_model(
        [
            {"role": "system", "content": DRAFT_SYSTEM},
            {"role": "user", "content": f"Plan:\n{plan.text}\n\nDisclosure:\n{disclosure.model_dump_json()}"},
        ],
        role="draft",
    )

    critique = call_model(
        [
            {"role": "system", "content": CRITIQUE_SYSTEM},
            {"role": "user", "content": draft.text},
        ],
        role="draft",
    )

    return Draft(
        disclosure_id=disclosure.id,
        claims=_split_claims(draft.text),
        specification=draft.text,
        critique_notes=[line for line in critique.text.splitlines() if line.strip()],
    )


def _split_claims(text: str) -> list[str]:
    claims = re.findall(r"^\s*\d+\.\s+(.+)$", text, flags=re.MULTILINE)
    return claims or [text.strip()]
