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
from agent.statute_reference import reference_block

# The MPEP legal reference is a fixed constant in every drafting/critique/revise
# template — identical across the ablation's empty and warmed arms, so it grounds
# the model in real law without touching the warmed-vs-empty delta.
_REF = reference_block()

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
    + _REF + "\n\n"
    "Loophole guardrails retrieved from memory for this technology class — close "
    "each one with explicit claim language; if none are listed, draft with "
    "standard care:\n{guardrails}"
)

CRITIQUE_SYSTEM = (
    "You are a hostile patent examiner. Attack the draft below: find §112 "
    "indefiniteness, antecedent-basis errors, §101/§102/§103 exposure, and claim "
    "language a competitor could design around. Ground every defect in the "
    "standards below and cite the MPEP section. Reply as a bulleted list of "
    "defects, most severe first.\n\n"
    + _REF + "\n\n"
    "Known loophole patterns retrieved from memory — check each explicitly; if "
    "none are listed, apply standard scrutiny:\n{guardrails}"
)

REVISE_SYSTEM = (
    "You are a patent attorney revising your own draft after a hostile examiner's "
    "critique. Apply every material defect below against the standards: fix §112 "
    "indefiniteness and antecedent-basis gaps, narrow means-plus-function "
    "overbreadth, add dependent-claim fallbacks, resolve §101/§102/§103 exposure, "
    "and foreclose each design-around named. Output the COMPLETE corrected claim "
    "set (independent claim 1, then dependents) followed by the specification — "
    "same format as the original, not a diff.\n\n"
    + _REF + "\n\n"
    "Loophole guardrails retrieved from memory for this technology class — keep "
    "each one closed as you revise; if none are listed, revise with standard "
    "care:\n{guardrails}"
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
    max_revise_rounds: int = 1,
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

    from agent.episodes import material_defects

    plan = turn("plan", PLAN_SYSTEM, disclosure.model_dump_json(), "tool")
    current = turn(
        "draft",
        DRAFT_SYSTEM.format(guardrails=slot),
        f"Plan:\n{plan}\n\nDisclosure:\n{disclosure.model_dump_json()}{notes_text}",
        "draft",
    )
    critique = turn("critique", CRITIQUE_SYSTEM.format(guardrails=slot), current, "draft")
    initial_critique = critique  # the mistakes MADE — what the episode learns from

    # Self-correction: feed the critique back and revise, until no material defect
    # remains or the round cap. Identical loop on both ablation arms; the only
    # variable is still the {guardrails} slot. Stub replies carry no defect, so
    # material_defects() is empty and this never runs — output stays byte-identical.
    rounds = 0
    while rounds < max_revise_rounds and material_defects(critique):
        current = turn(
            f"revise-{rounds + 1}",
            REVISE_SYSTEM.format(guardrails=slot),
            f"Draft:\n{current}\n\nExaminer critique:\n{critique}",
            "draft",
        )
        rounds += 1
        if rounds < max_revise_rounds:  # skip the re-critique after the last permitted revise
            critique = turn(f"critique-{rounds + 1}", CRITIQUE_SYSTEM.format(guardrails=slot), current, "draft")

    result = Draft(
        disclosure_id=disclosure.id,
        claims=_split_claims(current),  # POST-revision (was the raw pre-critique draft)
        specification=current,
        critique_notes=[line for line in initial_critique.splitlines() if line.strip()],
        loopholes_closed=[r.id for r in guardrails],
    )

    # Episodic write (B2): opt-in AND env-gated. The eval harness never passes a
    # sink, so no env flip can make the judged ablation mutate memory.
    if episode_sink is not None and __import__("airtight").config.EPISODES_ENABLED:
        from agent.episodes import compress_run

        mode = "stub" if __import__("airtight").config.MODE == "stub" else "live"
        episode_sink.record(compress_run(disclosure, guardrails, result, mode))

    return result


# A claim marker: line start, at most a small indent, optional markdown emphasis
# around the number ("**1.**", "__1.__", "1)", "1."). The indent bound and the
# emphasis handling both matter — a nested "(a)"/"i." limitation must NOT read as
# a new claim, and a bolded "**1.**" MUST read as one.
_CLAIM_MARK = re.compile(
    r"^[ \t]{0,3}(?:\*{1,2}|_{1,2})?(\d{1,3})[.)](?:\*{1,2}|_{1,2})?[ \t]+",
    re.MULTILINE,
)

# Where claims stop and prose begins. `judge.count_defects` scores claims and the
# specification as separate arguments, so letting the spec bleed into the last
# claim inflates one arm's scoring target against the other's.
_SPEC_HEAD = re.compile(
    r"^\W*(?:specification|detailed\s+description|abstract)\b",
    re.MULTILINE | re.IGNORECASE,
)


def _split_claims(text: str) -> list[str]:
    """Split a drafted claim set into individual claims.

    **Formatting-insensitive by contract.** `**1.**` and `1.` must yield the same
    claims, and each claim must keep its full multi-line body.

    Both properties are load-bearing for the M4 ablation, which judges two arms
    against each other. The original regex (`^\\s*\\d+\\.\\s+(.+)$`) broke both:
    markdown bold defeated it, so those drafts fell through to the whole-text
    fallback and were judged on the entire document *including the
    specification*, while plainly-numbered drafts parsed and were truncated to
    each claim's FIRST LINE by `(.+)$`. Whether an arm took the long or short
    path came down to formatting the model happened to choose that turn, so the
    judge scored paired arms on targets differing by up to 13x and the
    empty-vs-warmed comparison measured markdown, not memory. Observed
    2026-07-18 in `results/ablation/20260718-183817`: 4 of 6 pairs asymmetric.
    """
    spec = _SPEC_HEAD.search(text)
    body = text[: spec.start()] if spec else text

    # Keep only the run that counts 1, 2, 3… — this drops stray numbered lines
    # (dates, citations) and any nested enumeration that cleared the indent bound.
    kept: list[re.Match] = []
    expected = 1
    for mark in _CLAIM_MARK.finditer(body):
        if int(mark.group(1)) == expected:
            kept.append(mark)
            expected += 1

    if not kept:
        return [text.strip()]

    claims = []
    for i, mark in enumerate(kept):
        end = kept[i + 1].start() if i + 1 < len(kept) else len(body)
        claim = body[mark.end() : end].strip()
        if claim:
            claims.append(claim)
    return claims or [text.strip()]
