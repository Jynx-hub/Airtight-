"""Live prior-art search (USPTO ODP) → §103 "distinguish over this" loopholes.

Finds the patents genuinely similar to a disclosure and turns each into a real
prior-art exposure the draft must overcome, so "find all the loopholes from
prior similar ones" draws on the actual art for THIS invention — not only the
pre-pulled corpus. The drafter then adds distinguishing limitations and the
examiner checks §102/§103 against real references.

Two invariants:
- **Product path only.** The M4 ablation never calls this (isolation by omission,
  like episodic writes), so its empty-vs-warmed comparison stays clean.
- **Results cross the HiddenLayer bus.** The external fetch is a `guarded_tool`,
  so a poisoned prior-art reference is caught on the tool_result hop and the
  search yields nothing rather than smuggling an injection into the draft.
"""

import json
import os
import re
import urllib.parse
import urllib.request

from airtight import Disclosure, LoopholeRecord
from airtight import guardrails as g

API = "https://api.uspto.gov/api/v1/patent/applications/search"
_STOP = frozenset("a an the of for to and or with in on at by from as is are be "
                  "method system apparatus device using based said comprising".split())
# Prior art is a real patent, but the §103 exposure is INFERRED (not a documented
# rejection), so it competes on rank and never takes a reserved statute slot —
# those are for ground-truth PTAB records (extraction_confidence >= 1.0).
PRIOR_ART_CONFIDENCE = 0.5


_MAX_TERMS = 6  # a long AND/OR over ODP returns junk; the CPC scope carries most relevance


def _query(disclosure: Disclosure) -> str:
    """The keyword clause: a few high-signal distinct terms, order-stable."""
    words = [w for w in re.findall(r"[a-z0-9]+", f"{disclosure.title} {disclosure.summary}".lower())
             if w not in _STOP and len(w) > 2]
    return " ".join(list(dict.fromkeys(words))[:_MAX_TERMS]) or disclosure.title


def _lucene(terms: str, cpc: str) -> str:
    """Assemble the fielded query, not free-text `q=<terms>` — mirrors data/pull_uspto.py.

    Plain terms match preexam/reissue/reexam wrappers that carry no CPC and no
    real claims, and effectively return the most recent filings rather than
    similar art. Scoping to granted REGULAR applications in the disclosure's CPC
    class is what makes the hits genuine §103 prior art to distinguish over.
    """
    parts = ['applicationMetaData.applicationStatusDescriptionText:"Patented Case"',
             'applicationMetaData.applicationTypeCategory:"REGULAR"']
    cpc = (cpc or "").strip()
    if cpc:
        parts.insert(0, f"applicationMetaData.cpcClassificationBag:{cpc}*")
    if terms.split():
        parts.append("(" + " OR ".join(terms.split()) + ")")  # OR for recall; rank sorts relevance
    return " AND ".join(parts)


def _fielded_query(disclosure: Disclosure) -> str:
    """The full query this module sends for a disclosure. Assembly only — the
    product path goes through `_search`, which builds the same string internally."""
    return _lucene(_query(disclosure), disclosure.technology_class)


def _fetch(terms: str, cpc: str, limit: int) -> list:
    """The raw ODP call. Split out of `_search` so the projection and the guard
    are testable without a network stub — the API key is read here, inside, so it
    is never a guarded arg and never reaches the analysis API."""
    key = os.getenv("USPTO_API_KEY", "")
    url = f"{API}?{urllib.parse.urlencode({'q': _lucene(terms, cpc), 'rows': limit})}"
    req = urllib.request.Request(url, headers={"X-API-KEY": key})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read()).get("patentFileWrapperDataBag", [])[:limit]


def _project(rec: dict) -> dict:
    """Reduce an ODP record to the two fields `_to_loophole` actually reads.

    This is the tool_result-hop twin of the `_lucene`-after-the-hop fix above:
    analyze what the draft actually consumes, not the raw transport envelope.

    A full ODP record is ~22k chars of filing metadata, and five of them put
    122k chars across the bus. AIDR quarantined every live search on
    ["personally_identifiable_information", "url", "denial_of_service"] — all
    three *correct* calls on benign data, because a patent record genuinely
    carries inventor names with correspondence addresses (PII), uspto.gov asset
    links (url), and enough bulk to read as resource exhaustion. TOOL_RESULT
    quarantines on any detected category, so `guarded_tool` swapped in the
    placeholder and `search_prior_art` returned [] — the same zero-hits symptom
    as the tool_call block, one hop later.

    Projecting fixes it without touching POLICY: the payload drops ~100x and the
    three categories lose their trigger, while `inventionTitle` — the only field
    that reaches the draft, hence the only injection vector — still crosses the
    bus and is still checked for prompt_injection.
    """
    meta = rec.get("applicationMetaData") or {}
    return {"applicationNumberText": rec.get("applicationNumberText"),
            "applicationMetaData": {"inventionTitle": meta.get("inventionTitle")}}


@g.guarded_tool
def _search(terms: str, cpc: str, limit: int) -> list:
    """The external fetch, wrapped so tool_call args + tool_result cross the
    HiddenLayer bus. The API key is read from env inside `_fetch` (never a guarded
    arg, so it is not sent to the analysis API).

    The guarded args are the **semantic** inputs — the disclosure-derived terms and
    the CPC class — and the Lucene string is assembled here, *after* the hop. That
    is deliberate and it is a precision fix, not a weakening: the terms and CPC are
    the only attacker-controlled surface (they come from user-submitted disclosure
    text), while the field names, quoted literals and AND/OR scaffolding are a fixed
    template this module emits. The endpoint is the hardcoded `API` constant and the
    key is read from env inside, so a caller cannot redirect the request.

    Passing the assembled string was a live demo-breaker: AIDR's prompt-injection
    classifier reads a 306-char Lucene expression (field:value pairs, quoted phrases,
    AND/OR) as an instruction-injection pattern and BLOCKed every search — 3/3
    deterministic, real event ids. Each fragment scored clean on its own; only the
    full assembly tripped it. `search_prior_art` swallows `GuardrailBlocked` and
    returns [], so with `AIRTIGHT_HL_ENABLED=true` live prior art silently returned
    zero hits on every disclosure. Verified after this change: an injection planted
    in the disclosure summary still BLOCKs on this hop (tests/test_prior_art.py).

    The return value is projected by `_project` for the same reason, one hop later —
    see that function.
    """
    return [_project(r) for r in _fetch(terms, cpc, limit) if isinstance(r, dict)]


def _to_loophole(rec: dict, disclosure: Disclosure) -> LoopholeRecord:
    meta = rec.get("applicationMetaData", {})
    app = rec.get("applicationNumberText", "unknown")
    title = str(meta.get("inventionTitle", "prior art"))[:90]
    return LoopholeRecord(
        id=f"priorart-{app}",
        pattern=f"§103 — prior art US application {app} discloses similar subject matter ('{title}')",
        claim_shape=f"claims overlapping: {title}",
        technology_class=disclosure.technology_class,
        remedy="add a novel limitation that distinguishes over this reference and claim the delta explicitly",
        source=f"USPTO ODP prior-art search · app {app}",
        statute="103",
        extraction_confidence=PRIOR_ART_CONFIDENCE,
    )


def search_prior_art(disclosure: Disclosure, limit: int = 5) -> list[LoopholeRecord]:
    """Return §103 loopholes for the prior art most similar to the disclosure.
    Degrades to [] on any failure — no key, network error, or a quarantined
    (poisoned) result — so a bad search never blocks or poisons a draft."""
    if not os.getenv("USPTO_API_KEY"):
        return []  # no key, no search
    try:
        raw = _search(_query(disclosure), disclosure.technology_class or "", limit)
    except Exception:
        return []
    if not isinstance(raw, list):
        return []  # guarded_tool returned the quarantine placeholder — poisoned result dropped
    return [_to_loophole(r, disclosure) for r in raw if isinstance(r, dict)]
