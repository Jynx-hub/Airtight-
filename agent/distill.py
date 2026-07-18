"""Turning free text into a LoopholeRecord — the one extraction contract.

Two producers share it. `data/distill_loopholes.py` mines real PTAB Final
Written Decisions (ground truth, confidence 1.0). `distill_text` below reads a
document admitted at ingest (untrusted, confidence 0.3). The *framing* differs
because the inputs differ; the JSON contract that parse_json and LoopholeRecord
depend on is defined once, here.

This lives in `agent/` rather than `data/` because `data` is not a packaged
module (see pyproject.toml) — `agent.ingest` importing from `data.` works from a
repo checkout and breaks in a wheel.
"""

import hashlib
import json
import re

from airtight import LoopholeRecord, call_model

# The output schema. Shared verbatim by both producers so a change to what the
# model must emit can't drift out of sync with what parse_json expects.
DISTILL_JSON_CONTRACT = (
    'Reply with JSON only: '
    '{"pattern": "<short loophole pattern>", "claim_shape": "<the kind of claim '
    'language that triggered it>", "remedy": "<how careful drafting would have '
    'foreclosed it>"}.'
)

# PTAB framing — a decision that actually held claims unpatentable.
# Byte-identical to the pre-split string; tests/test_distill.py pins its sha256
# so the ground-truth producer's prompt cannot drift silently.
DISTILL_SYSTEM = (
    "You are a patent analyst. A PTAB Final Written Decision held patent claims "
    "unpatentable. From the real decision facts below, infer the ONE core loophole "
    "that killed the claims — the claim-drafting weakness a competitor or petitioner "
    "exploited. " + DISTILL_JSON_CONTRACT
)

# Ingest framing. Deliberately NOT DISTILL_SYSTEM: that prompt asserts a PTAB
# decision held claims unpatentable, which is false about an arbitrary ingested
# document. Feeding the model a false premise to get a plausible-looking record
# is how fabricated memory gets minted.
INGEST_SYSTEM = (
    "You are a patent analyst reading a prior-art or prosecution document. From "
    "the document text below, infer the ONE claim-drafting loophole it most "
    "directly evidences — the weakness an examiner or petitioner could exploit "
    "against a claim in this area. If the document evidences no such weakness, "
    "reply with an empty JSON object. " + DISTILL_JSON_CONTRACT
)

# A 200-page PDF must not blow the context window or the token bill. The slice
# is also what the record id digests, so the id describes exactly what produced it.
MAX_DISTILL_CHARS = 6000

# Records inferred from an untrusted document are not ground truth. db/schema.sql
# specced this scale: 1.0 = rule-matched, lower = heuristic.
INGESTED_CONFIDENCE = 0.3


def parse_json(text: str) -> dict | None:
    """Pull the first {...} out of a reply. Greedy and DOTALL — note this cannot
    parse a top-level array, which is part of why distillation is one record per
    call rather than a list."""
    m = re.search(r"\{.*\}", text, flags=re.DOTALL)
    if not m:
        return None
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError:
        return None


def _normalize_tech_class(tech_class: str) -> str:
    """CPC only ("G06F", "H04L") for the ingest path.

    Retrieval matches rec.technology_class against Disclosure.technology_class,
    which is a CPC class. A USPTO Technology Center string ("TC2100") can never
    match one, so a record built with it loses the highest-order term of the sort
    key permanently — raise rather than mint a half-retrievable record.

    Known asymmetry, deliberately not "fixed" here: `data/distill_loopholes.py`
    mints exactly `TC{n}` for every PTAB record it writes, so the two producers
    disagree about this field. That is a real defect in the *ground-truth* path —
    those records are structurally outranked by any CPC-classed record — but
    rewriting it would change the corpus the GPU re-run measures, so it is filed
    on the board rather than changed mid-window. Ingest holds the stricter line
    because ingest is new and has no corpus to invalidate.
    """
    tc = (tech_class or "").strip().upper()
    if not tc:
        raise ValueError("tech_class is required — retrieval matches on CPC class")
    if tc.startswith("TC"):
        raise ValueError(
            f"tech_class {tech_class!r} is a USPTO Technology Center, not a CPC class. "
            "Retrieval matches CPC (e.g. 'G06F'); a TC-shaped class never matches. "
            "(data/distill_loopholes.py mints TC-shaped classes — see docs/WORKSTREAMS.md.)"
        )
    return tc[:4]


def _safe_source(source: str) -> str:
    """Neutralize statute tokens in an attacker-controlled filename.

    statute_of matches `[§\\s(]\\s*(101|102|103|112)\\b` over pattern then source,
    so a file named "prior art §103.pdf" would otherwise set the record's statute
    and steer which diversify bucket it lands in — and since INGEST_SYSTEM never
    asks the model to encode a statute, `source` is the *usual* fallback, not an
    edge case.

    Stripping `§()` is not enough: the character class also accepts whitespace,
    so "Office Action 101.pdf" still matches. Punch the digits themselves out.
    """
    return re.sub(r"\b(101|102|103|112)\b", "###", re.sub(r"[§()]", "", source)).strip()


def distill_text(text: str, source: str, tech_class: str) -> list[LoopholeRecord]:
    """Distill one admitted document into at most one LoopholeRecord.

    Returns a list because callers merge it into a store, but the arity is one by
    construction: one model call, one record. That bound is structural rather
    than a cap applied afterwards — the failure mode to avoid is compress_run's,
    which appends one record per *line* of a reply and lets self-generated noise
    outgrow the real corpus.

    Callers must pass text that already cleared the ingested_document hop.
    """
    tc = _normalize_tech_class(tech_class)
    name = _safe_source(source)
    excerpt = text[:MAX_DISTILL_CHARS]

    # Document text rides as a `user` message, never `system`: that routes it
    # through the doorway's USER_PROMPT hop, so an ingested document crosses the
    # HiddenLayer bus a second time on its way to the model.
    reply = call_model(
        [{"role": "system", "content": INGEST_SYSTEM},
         {"role": "user", "content": f"DOCUMENT: {name}\n\n{excerpt}"}],
        role="distill", max_tokens=400,
    )
    data = parse_json(reply.text) or {}
    if not data.get("pattern"):
        return []

    # Content-addressed on the *input*, never the reply — a nondeterministic live
    # model must not be able to mint a second id for the same document. Re-ingest
    # is therefore idempotent: same document, same id, one file.
    digest = hashlib.sha256(f"{name}\0{excerpt}".encode()).hexdigest()[:12]
    stub = reply.mode == "stub"
    # The provenance marker rides in `pattern`, not only in `source`, because
    # loop.render_guardrails renders id/statute/pattern/claim_shape/remedy and
    # drops source and extraction_confidence. A marker the drafting prompt never
    # shows protects nothing at the point of use: an inferred record would reach
    # the model formatted identically to a PTAB-mined one. Prefixing the rendered
    # field is what makes the distinction visible where it matters — and it keeps
    # the fix out of agent/loop.py, so the ablation's scaffold hash is untouched.
    provenance = "[UNVERIFIED — inferred from an untrusted document]"
    if stub:
        provenance = "[UNVERIFIED STUB — not a real extraction]"
    return [LoopholeRecord(
        id=f"ing-{digest}",
        pattern=f"{provenance} {str(data['pattern'])[:200]}",
        claim_shape=str(data.get("claim_shape", ""))[:300],
        technology_class=tc,
        remedy=str(data.get("remedy", ""))[:300],
        source=f"INGESTED {name} — agent-extracted from an untrusted document"
        + ("  [STUB — not real]" if stub else ""),
        extraction_confidence=INGESTED_CONFIDENCE,
    )]
