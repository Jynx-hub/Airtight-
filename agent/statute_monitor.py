"""Statute currency monitor — keep the legal standards in
`agent/statute_reference.py` from silently going stale.

Software/electronics patent law almost never moves by *statute* (the AIA, 2011,
was the last big one). It moves by **case law** (Alice, KSR, Nautilus, Williamson
v. Citrix — all judicial) and by **USPTO guidance** (subject-matter-eligibility
updates, MPEP revisions). So this monitor watches those first; Congress bills are
a thin "what's coming" flag, not the main signal.

    export COURTLISTENER_API_TOKEN=...   # free at courtlistener.com
    export LEGISCAN_API_KEY=...          # free at legiscan.com/legiscan  (state + federal bills)
    export CONGRESS_API_KEY=...          # free at api.congress.gov       (federal bills only)
    python -m agent.statute_monitor --fetch                 # Fed. Register (keyless) + any keyed source
    python -m agent.statute_monitor --fetch --source fedreg
    python -m agent.statute_monitor --fake                  # offline rehearsal, no network/keys
    python -m agent.statute_monitor --review                # pending proposals + the exact STATUTES paste
    python -m agent.statute_monitor --approve <id>          # record the operator's out-of-band decision
    python -m agent.statute_monitor --reject  <id>

Why this is a *proposal queue* and not an auto-writer into STATUTES
------------------------------------------------------------------
`STATUTES` is hand-curated and accuracy-critical ("a wrong standard is worse than
none" — CLAUDE.md), and `reference_block()` feeds a *deterministic* prompt-template
hash the M4 ablation proof depends on (`test_reference_is_constant_across_ablation_arms`,
`test_reference_block_is_deterministic_and_cited`). A live write into STATUTES mid-run
would corrupt that proof. So this module mirrors the repo's **Policy-Advisor** shape:

    monitor detects  ->  proposes a candidate (separate file)  ->  operator approves
    out-of-band  ->  human pastes the verified entry into STATUTES and commits it.

Admission is a deliberate, between-runs, *human* step. The monitor never edits
`statute_reference.py` and never imports `STATUTES` — see
`tests/test_statute_monitor.py::test_monitor_never_touches_the_reference`.

Never fabricates (carried over from `data/pull_uspto.py`): no source URL, no entry;
a candidate whose statutory basis can't be resolved from its own text is dropped,
not guessed at.
"""

import argparse
import hashlib
import json
import os
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from pydantic import BaseModel

PROPOSALS = Path(__file__).resolve().parent / "statute_proposals.jsonl"

# The six failure modes STATUTES already keys on — a proposal is only actionable
# if we can bind it to one of these (or flag it as a genuinely new basis).
STATUTE_KEYS = ("101", "102", "103", "112a", "112b", "112f")

# Domain gate (CLAUDE.md — software & electronics only). A candidate must name a
# patent statutory basis AND read as software/electronics, or it's out of scope.
_BASIS_TERMS = ("101", "102", "103", "112", "eligibility", "obviousness",
                "anticipation", "definiteness", "written description", "enablement",
                "means-plus-function", "means for", "patentab")
_DOMAIN_TERMS = ("software", "computer-implemented", "computer implemented",
                 "algorithm", "abstract idea", "alice", "mayo", "processor",
                 "electronic", "semiconductor", "circuit", "hardware", "firmware",
                 "machine learning", "neural", "data processing", "§101", "112(f)")


class StatuteProposal(BaseModel):
    """A candidate change to the legal standards, awaiting operator sign-off.

    Never lands in STATUTES automatically — `render_admission` produces the exact
    line a human reviews, pastes, and commits (the Policy-Advisor out-of-band step).
    """

    id: str                       # sha256(source_url + title)[:12] — stable, dedup key
    statute: str                  # one of STATUTE_KEYS, or "new" for an unmapped basis
    title: str
    holding: str                  # one-paragraph standard/change, ideally with an actionable fix
    citation: str                 # e.g. "Fed. Cir. 2026", "USPTO 2026 SME Update", "MPEP 2106 (rev.)"
    source_url: str               # must be present — the "never fabricates" anchor
    source_type: str              # "case" | "guidance" | "bill"
    date: str = ""                # publication date if the source gives one
    rationale: str = ""           # why it's software/electronics-relevant
    status: str = "pending"       # pending | approved | rejected


def _classify_statute(text: str) -> str:
    """Bind free text to a STATUTES key, '' if no basis is discernible.

    112 is split into (a)/(b)/(f); when the text says 112 without a sub-part we
    can't know which standard changed, so we return the bare '112' as a signal to
    the operator rather than guessing a sub-key. '' means drop (never fabricates)."""
    low = text.lower()
    if "112(f)" in low or "means-plus-function" in low or "means for" in low:
        return "112f"
    if "112(b)" in low or "definiteness" in low or "indefinite" in low or "antecedent" in low:
        return "112b"
    if "112(a)" in low or "written description" in low or "enablement" in low or "enable" in low:
        return "112a"
    if "112" in low:
        return "112"  # basis is 112 but sub-part unresolved — operator decides
    if "103" in low or "obvious" in low:
        return "103"
    if "102" in low or "anticipat" in low:
        return "102"
    if "101" in low or "eligib" in low or "abstract idea" in low or "alice" in low:
        return "101"
    return ""


def _is_relevant(text: str) -> bool:
    """Software/electronics patent-standard gate (CLAUDE.md domain scope)."""
    low = text.lower()
    return (any(t in low for t in _BASIS_TERMS)
            and any(t in low for t in _DOMAIN_TERMS))


def _make_id(source_url: str, title: str) -> str:
    return hashlib.sha256(f"{source_url}\n{title}".encode()).hexdigest()[:12]


def to_proposal(*, title: str, holding: str, citation: str, source_url: str,
                source_type: str, date: str = "") -> StatuteProposal | None:
    """Build a proposal, or None if it must be dropped.

    Drops (never fabricates) when: no source URL, no citation, out of software/
    electronics scope, or no statutory basis resolvable from the candidate's own
    text. A dropped candidate is silence, not a guess."""
    if not source_url or not citation:
        return None
    blob = f"{title}\n{holding}\n{citation}"
    if not _is_relevant(blob):
        return None
    statute = _classify_statute(blob)
    if not statute:
        return None
    # Keep a bare "112" visible as an operator signal (sub-part unresolved);
    # only a truly unmappable basis collapses to "new".
    return StatuteProposal(
        id=_make_id(source_url, title),
        statute=statute if statute in STATUTE_KEYS or statute == "112" else "new",
        title=title.strip(),
        holding=holding.strip(),
        citation=citation.strip(),
        source_url=source_url.strip(),
        source_type=source_type,
        date=date,
        rationale="matched a software/electronics patent-standard signal",
    )


# ---------------------------------------------------------------------------
# The proposal queue (jsonl, append-only, dedup by id)
# ---------------------------------------------------------------------------

def load_proposals(path: Path = PROPOSALS) -> list[StatuteProposal]:
    if not path.exists():
        return []
    out = []
    for line in path.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(StatuteProposal(**json.loads(line)))
    return out


def _write_all(proposals: list[StatuteProposal], path: Path = PROPOSALS) -> None:
    path.write_text("".join(p.model_dump_json() + "\n" for p in proposals))


def add_proposals(candidates: list[StatuteProposal], path: Path = PROPOSALS) -> int:
    """Append new candidates; skip any id already in the queue. Returns #added.

    Dedup by id (source_url + title) so re-running --fetch is idempotent and an
    operator's earlier approve/reject on the same item is never overwritten."""
    existing = load_proposals(path)
    seen = {p.id for p in existing}
    added = [c for c in candidates if c and c.id not in seen]
    if added:
        _write_all(existing + added, path)
    return len(added)


def set_status(proposal_id: str, status: str, path: Path = PROPOSALS) -> bool:
    proposals = load_proposals(path)
    hit = False
    for p in proposals:
        if p.id == proposal_id:
            p.status, hit = status, True
    if hit:
        _write_all(proposals, path)
    return hit


def render_admission(p: StatuteProposal) -> str:
    """The exact review card + the STATUTES entry a human pastes after verifying.

    We render the paste block but never apply it — admission stays a deliberate
    human commit so the ablation's deterministic template hash only ever changes
    between runs, by a person, on a verified citation."""
    key = p.statute if p.statute in STATUTE_KEYS else "<assign-a-key>"
    # json.dumps, not raw f-string interpolation: a holding/citation containing a
    # double quote ('the "abstract idea" doctrine', a quoted claim term) would
    # otherwise emit unparseable Python. ensure_ascii=False keeps § and the
    # double-quote style STATUTES uses.
    holding = json.dumps(p.holding, ensure_ascii=False)
    citation = json.dumps(p.citation, ensure_ascii=False)
    snippet = (f'    "{key}": (\n'
               f'        {holding},\n'
               f'        {citation},\n'
               f'    ),')
    return (
        f"[{p.id}] ({p.status}) §{p.statute} — {p.title}\n"
        f"    cite:   {p.citation}\n"
        f"    source: {p.source_url}\n"
        f"    {p.holding}\n"
        f"    ── verify the citation, then paste into agent/statute_reference.py STATUTES ──\n"
        f"{snippet}"
    )


# ---------------------------------------------------------------------------
# Sources. Keyless where the API allows; "no key, no pull" everywhere else.
# ---------------------------------------------------------------------------

REQUEST_SPACING = 0.4
MAX_RETRIES = 5
TIMEOUT = 30
_last_call = 0.0


def _fetch(url: str, headers: dict | None = None) -> bytes:
    """GET with polite spacing + 429 backoff, matching data/pull_uspto._fetch."""
    global _last_call
    for attempt in range(MAX_RETRIES):
        gap = time.monotonic() - _last_call
        if gap < REQUEST_SPACING:
            time.sleep(REQUEST_SPACING - gap)
        req = urllib.request.Request(url, headers=headers or {})
        try:
            with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
                return resp.read()
        except urllib.error.HTTPError as exc:
            if exc.code != 429 or attempt == MAX_RETRIES - 1:
                raise
            wait = float(exc.headers.get("Retry-After") or 2 ** (attempt + 1))
            print(f"    rate limited — waiting {wait:.0f}s", file=sys.stderr)
            time.sleep(wait)
        finally:
            _last_call = time.monotonic()
    raise RuntimeError("unreachable")


def fetch_fedreg(term: str = "patent subject matter eligibility",
                 per_page: int = 20) -> list[StatuteProposal]:
    """USPTO documents from the Federal Register API (free, keyless).

    This is the guidance channel: SME updates and MPEP-driving notices land here."""
    params = {
        "conditions[agencies][]": "patent-and-trademark-office",
        "conditions[term]": term,
        "order": "newest",
        "per_page": str(per_page),
        "fields[]": ["title", "abstract", "html_url", "publication_date",
                     "document_number"],
    }
    url = "https://www.federalregister.gov/api/v1/documents.json?" + urllib.parse.urlencode(
        params, doseq=True)
    data = json.loads(_fetch(url))
    out = []
    for doc in data.get("results", []):
        p = to_proposal(
            title=doc.get("title", ""),
            holding=(doc.get("abstract") or doc.get("title") or "").strip(),
            citation=f"Fed. Reg. {doc.get('document_number', '?')} "
                     f"({doc.get('publication_date', '?')})",
            source_url=doc.get("html_url", ""),
            source_type="guidance",
            date=doc.get("publication_date", ""),
        )
        if p:
            out.append(p)
    return out


def fetch_courtlistener(query: str = "35 U.S.C. 101 eligibility",
                        max_results: int = 20) -> list[StatuteProposal]:
    """Precedential CAFC opinions via CourtListener. no token, no pull."""
    token = os.environ.get("COURTLISTENER_API_TOKEN")
    if not token:
        print("    COURTLISTENER_API_TOKEN unset — skipping case-law source "
              "(no key, no pull)", file=sys.stderr)
        return []
    params = {"q": query, "court": "cafc", "type": "o", "precedential_status": "Published",
              "order_by": "dateFiled desc"}
    url = "https://www.courtlistener.com/api/rest/v4/search/?" + urllib.parse.urlencode(params)
    data = json.loads(_fetch(url, headers={"Authorization": f"Token {token}"}))
    out = []
    for r in data.get("results", [])[:max_results]:
        cite = (r.get("citation") or [""])[0] if isinstance(r.get("citation"), list) else ""
        p = to_proposal(
            title=r.get("caseName", ""),
            holding=(r.get("snippet") or r.get("caseName") or "").strip(),
            citation=cite or f"Fed. Cir. ({r.get('dateFiled', '?')})",
            source_url="https://www.courtlistener.com" + r.get("absolute_url", ""),
            source_type="case",
            date=r.get("dateFiled", ""),
        )
        if p:
            out.append(p)
    return out


def fetch_congress(query: str = "patent", congress: int = 119,
                   max_results: int = 20) -> list[StatuteProposal]:
    """Title-35 bills via the Congress.gov API. no key, no pull. Thinnest signal:
    a bill isn't operative until enacted, so these land as 'what's coming' flags."""
    key = os.environ.get("CONGRESS_API_KEY")
    if not key:
        print("    CONGRESS_API_KEY unset — skipping bills source (no key, no pull)",
              file=sys.stderr)
        return []
    params = {"query": query, "api_key": key, "limit": str(max_results),
              "sort": "updateDate+desc"}
    url = f"https://api.congress.gov/v3/bill/{congress}?" + urllib.parse.urlencode(params)
    data = json.loads(_fetch(url))
    out = []
    for b in data.get("bills", [])[:max_results]:
        num = f"{b.get('type', '')}{b.get('number', '')}"
        p = to_proposal(
            title=b.get("title", ""),
            holding=b.get("title", ""),  # bill search gives no body; title is all we have
            citation=f"{num}, {congress}th Cong. ({b.get('updateDate', '?')})",
            source_url=b.get("url", ""),
            source_type="bill",
            date=b.get("updateDate", ""),
        )
        if p:
            out.append(p)
    return out


def fetch_legiscan(query: str = "patent AND (software OR eligibility OR semiconductor)",
                   state: str = "ALL", max_results: int = 30) -> list[StatuteProposal]:
    """State + federal legislation via LegiScan's getSearch op. no key, no pull.

    LegiScan (legiscan.com/legiscan — free key) tracks all 50 states + Congress, so
    it catches state-level tech legislation Congress.gov misses. Like any bill source
    it's a 'what's coming' flag: not operative until enacted. getSearch returns a
    title + last action per hit, so no second getBill call is needed to build a
    proposal. `state='ALL'` searches every state and Congress; pass 'US' for federal
    only, or a postal code (e.g. 'CA') for one state."""
    key = os.environ.get("LEGISCAN_API_KEY")
    if not key:
        print("    LEGISCAN_API_KEY unset — skipping LegiScan (no key, no pull)",
              file=sys.stderr)
        return []
    params = {"key": key, "op": "getSearch", "state": state, "query": query}
    url = "https://api.legiscan.com/?" + urllib.parse.urlencode(params)
    data = json.loads(_fetch(url))
    result = data.get("searchresult", {})
    out = []
    # getSearch keys hits as "0","1",… alongside a "summary" object — skip summary.
    hits = [v for k, v in result.items() if k != "summary" and isinstance(v, dict)]
    for h in hits[:max_results]:
        action = h.get("last_action", "")
        p = to_proposal(
            title=h.get("title", h.get("bill_number", "")),
            holding=f"{h.get('title', '')} — {action}".strip(" —"),
            citation=f"{h.get('bill_number', '?')} "
                     f"({h.get('last_action_date') or h.get('state', '?')})",
            source_url=h.get("url", ""),
            source_type="bill",
            date=h.get("last_action_date", ""),
        )
        if p:
            out.append(p)
    return out


SOURCES = {"fedreg": fetch_fedreg, "courtlistener": fetch_courtlistener,
           "legiscan": fetch_legiscan, "congress": fetch_congress}


# One offline candidate for rehearsing --fetch with no network/keys (mirrors
# ingest.py's FAKE_CLEAN/FAKE_DETECT and the "build against the mock first" rule).
FAKE_SOURCE = [dict(
    title="In re Example Networks (hypothetical) — computer-implemented claim held eligible",
    holding="A claim reciting a specific improvement to network cache coherency, rather "
            "than the abstract idea of data synchronization on a generic computer, is "
            "§101-eligible at Step 2A Prong 2. Fix: tie the claim to the concrete technical "
            "improvement, not the result.",
    citation="Fed. Cir. (rehearsal fixture — not real law)",
    source_url="https://example.invalid/rehearsal/in-re-example-networks",
    source_type="case",
    date="2026-07-18",
)]


def _fetch_all(sources: list[str]) -> list[StatuteProposal]:
    out = []
    for name in sources:
        try:
            found = SOURCES[name]()
            print(f"  {name}: {len(found)} relevant candidate(s)", file=sys.stderr)
            out.extend(found)
        except Exception as exc:  # one dead source must not sink the others
            print(f"  {name}: skipped ({exc})", file=sys.stderr)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--fetch", action="store_true", help="pull + filter into the queue")
    ap.add_argument("--source", choices=list(SOURCES) + ["all"], default="all")
    ap.add_argument("--fake", action="store_true",
                    help="rehearse --fetch with an offline fixture (no network/keys)")
    ap.add_argument("--review", action="store_true", help="show pending proposals")
    ap.add_argument("--approve", metavar="ID")
    ap.add_argument("--reject", metavar="ID")
    args = ap.parse_args()

    if args.fake:
        cands = [to_proposal(**raw) for raw in FAKE_SOURCE]
        n = add_proposals([c for c in cands if c])
        print(f"rehearsal: {n} proposal(s) added to {PROPOSALS.name}")
        return 0

    if args.fetch:
        names = list(SOURCES) if args.source == "all" else [args.source]
        n = add_proposals(_fetch_all(names))
        print(f"{n} new proposal(s) added to {PROPOSALS.name}")
        return 0

    if args.approve:
        ok = set_status(args.approve, "approved")
        print("approved" if ok else f"no proposal {args.approve}", file=sys.stderr)
        return 0 if ok else 1

    if args.reject:
        ok = set_status(args.reject, "rejected")
        print("rejected" if ok else f"no proposal {args.reject}", file=sys.stderr)
        return 0 if ok else 1

    if args.review:
        pending = [p for p in load_proposals() if p.status == "pending"]
        if not pending:
            print("no pending proposals")
            return 0
        print(f"{len(pending)} pending proposal(s):\n")
        for p in pending:
            print(render_admission(p))
            print()
        return 0

    ap.print_help()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
