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

REVISE_SYSTEM = (
    "You are a patent attorney revising your own draft after a hostile examiner's "
    "critique. Rewrite the claims (keep the numbering) and the specification so every "
    "listed defect is fixed with explicit claim language. Reply with the full revised "
    "draft only — numbered claims, then the specification — no commentary.\n\n"
    "Loophole guardrails retrieved from memory — keep each one closed:\n{guardrails}"
)

GUARDRAILS_EMPTY = "(none on record)"

# B1: how many revise passes to run before giving up on convergence. Each pass feeds
# the examiner's defects back and re-critiques; the loop stops early the moment a pass
# surfaces no NEW defect. This is the difference between self-critique and self-correction.
MAX_REVISE_ROUNDS = 2


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
    revise_rounds: int = MAX_REVISE_ROUNDS,
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

    # B1: self-CORRECTION, not just self-critique. Feed the examiner's defects back and
    # revise, then re-critique; repeat until a pass finds no NEW defect (converged) or we
    # hit revise_rounds. Before this, the run ended with the examiner's defects still in
    # the draft, and `specification` was even the *pre-critique* text.
    findings = [line for line in critique.splitlines() if line.strip()]
    seen = set(findings)
    for r in range(revise_rounds):
        if not findings:
            break
        draft = turn(
            f"revise{r + 1}",
            REVISE_SYSTEM.format(guardrails=slot),
            f"Draft:\n{draft}\n\nExaminer defects to fix:\n{critique}",
            "draft",
        )
        critique = turn(f"critique{r + 1}", CRITIQUE_SYSTEM.format(guardrails=slot), draft, "draft")
        findings = [line for line in critique.splitlines() if line.strip()]
        new = [f for f in findings if f not in seen]
        if not new:  # examiner surfaced nothing new — the draft has converged
            break
        seen.update(findings)

    result = Draft(
        disclosure_id=disclosure.id,
        claims=_split_claims(draft),          # the revised claims
        specification=draft,                  # the revised draft, not the pre-critique text
        critique_notes=findings,              # the FINAL examiner pass (what still stands, if anything)
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
