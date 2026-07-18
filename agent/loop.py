"""The work loop: plan → draft → self-critique → assemble.

Plain Python on purpose — LangChain Deep Agents is an M3 option, not a day-one
dependency. Every model turn goes through the doorway; nothing else in this
repo may talk to a model.

The {guardrails} slot is the M4 ablation's only variable: the template strings
are byte-identical in both conditions, and only the slot's rendered content
differs (empty → GUARDRAILS_EMPTY, warmed → retrieved records). Do not add
condition-dependent text anywhere else.
"""

import re

from airtight import Disclosure, Draft, LoopholeRecord, call_model

PLAN_SYSTEM = (
    "You are the planning module of a patent-drafting agent. Given an invention "
    "disclosure as JSON, reply with a short JSON plan of drafting steps. Reply "
    "with JSON only."
)

DRAFT_SYSTEM = (
    "You are a patent attorney. Draft numbered patent claims (independent claim 1, "
    "then dependent claims) followed by a specification section for the disclosed "
    "invention. Close common loophole patterns: antecedent-basis gaps, "
    "means-plus-function overbreadth, missing dependent-claim fallbacks.\n\n"
    "Loophole guardrails retrieved from memory for this technology class — close "
    "each one with explicit claim language; if none are listed, draft with "
    "standard care:\n{guardrails}"
)

CRITIQUE_SYSTEM = (
    "You are a hostile patent examiner. Attack the draft below: find §112 "
    "indefiniteness, antecedent-basis errors, §102/§103 exposure, and claim "
    "language a competitor could design around. Reply as a bulleted list of "
    "defects, most severe first.\n\n"
    "Known loophole patterns retrieved from memory — check each explicitly; if "
    "none are listed, apply standard scrutiny:\n{guardrails}"
)

GUARDRAILS_EMPTY = "(none on record)"


def render_guardrails(records: list[LoopholeRecord]) -> str:
    if not records:
        return GUARDRAILS_EMPTY
    return "\n".join(
        f"- [{r.id}]{' §' + r.statute if r.statute else ''} pattern: {r.pattern} | "
        f"risky claim shape: {r.claim_shape} | remedy: {r.remedy}"
        for r in records
    )


def draft_patent(
    disclosure: Disclosure,
    guardrails: list[LoopholeRecord] | None = None,
    transcript: list | None = None,
    fan_out: bool = False,
    max_workers: int | None = None,
    episode_sink=None,
    **gen_kwargs,
) -> Draft:
    guardrails = guardrails or []
    slot = render_guardrails(guardrails)

    def turn(name: str, system: str, user: str, role: str) -> str:
        messages = [{"role": "system", "content": system}, {"role": "user", "content": user}]
        reply = call_model(messages, role=role, **gen_kwargs)
        if transcript is not None:
            transcript.append({"turn": name, "messages": messages, "reply": reply.text})
        return reply.text

    # Concurrent sub-agent retrieval (opt-in). Notes fold into the draft USER
    # message only — never the SYSTEM templates the ablation hashes.
    notes_text = ""
    if fan_out and guardrails:
        from agent.subagents import fan_out_retrieval, notes_block

        notes_text = notes_block(fan_out_retrieval(disclosure, guardrails, max_workers, **gen_kwargs))

    plan = turn("plan", PLAN_SYSTEM, disclosure.model_dump_json(), "tool")
    draft = turn(
        "draft",
        DRAFT_SYSTEM.format(guardrails=slot),
        f"Plan:\n{plan}\n\nDisclosure:\n{disclosure.model_dump_json()}{notes_text}",
        "draft",
    )
    critique = turn("critique", CRITIQUE_SYSTEM.format(guardrails=slot), draft, "draft")

    result = Draft(
        disclosure_id=disclosure.id,
        claims=_split_claims(draft),
        specification=draft,
        critique_notes=[line for line in critique.splitlines() if line.strip()],
        loopholes_closed=[r.id for r in guardrails],
    )

    # Episodic write (opt-in). The eval harness never passes a sink, so the
    # judged ablation never mutates memory — see agent/episodes.py.
    if episode_sink is not None:
        from agent.episodes import compress_run

        mode = "stub" if __import__("airtight").config.MODE == "stub" else "live"
        episode_sink.record(compress_run(disclosure, guardrails, result, mode))

    return result


def _split_claims(text: str) -> list[str]:
    claims = re.findall(r"^\s*\d+\.\s+(.+)$", text, flags=re.MULTILINE)
    return claims or [text.strip()]
