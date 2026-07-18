"""Pull real USPTO data into the Airtight shapes via the ODP API.

Endpoints + field mappings VERIFIED against live responses 2026-07-18 (needs a
free key — set USPTO_API_KEY; register at https://data.uspto.gov):
  patents  GET https://api.uspto.gov/api/v1/patent/applications/search
  ptab     GET https://api.uspto.gov/api/v1/patent/trials/decisions/search
  docs     GET https://api.uspto.gov/api/v1/patent/applications/{app}/documents

    export USPTO_API_KEY=...
    python -m data.pull_uspto --groundtruth --cpc G06N --limit 50   # E1 + E2
    python -m data.pull_uspto --patents --query "neural network cache" --cpc G06
    python -m data.pull_uspto --ptab --query obviousness --limit 30

--groundtruth is the one that feeds the M4 ablation. Search returns metadata
only — no abstract, no claims — so it walks the file wrapper, where the abstract
(ABST), the claims (CLM) and the examiner's rejections (CTNF/CTFR) are each a
separate document downloadable as a tar of WIPO ST.96 XML. Out come real
Disclosures (real abstract + real claims) and LoopholeRecords mined from the
formal rejection statements, one per rejected independent claim.

--patents is the thin path: real title/CPC/inventors from search metadata, with
no invention text behind it. PTAB decisions -> raw records for a distiller.

Never fabricates: no key, no pull; a record whose claims or CPC cannot be
resolved is dropped rather than guessed at.
"""

import argparse
import hashlib
import io
import json
import os
import re
import sys
import tarfile
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from pathlib import Path

from airtight import Disclosure, LoopholeRecord

API = "https://api.uspto.gov/api/v1"
DATA = Path(__file__).resolve().parent


def _get(path: str, params: dict, api_key: str) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    return json.loads(_fetch(url, api_key))  # shared spacing + 429 backoff


def _clean_cpc(cpc_bag: list) -> str:
    if not cpc_bag:
        return ""
    return "".join(str(cpc_bag[0]).split())  # "G06N  20/20" -> "G06N20/20"


def _pick_cpc(cpc_bag: list, prefix: str) -> str:
    """The CPC the record was selected on — not just whichever sorts first.

    A G06N hit routinely lists H04B/H04W first, so `cpc_bag[0]` would label a
    machine-learning patent as radio. Prefer an entry matching the requested
    prefix; fall back to the first only when nothing matches.
    """
    cleaned = ["".join(str(c).split()) for c in cpc_bag if str(c).strip()]
    if not cleaned:
        return ""
    if prefix:
        for c in cleaned:
            if c.upper().startswith(prefix.upper()):
                return c
    return cleaned[0]


def _map_application(rec: dict, cpc_prefix: str = "") -> Disclosure | None:
    meta = rec.get("applicationMetaData", {})
    app_no = rec.get("applicationNumberText", "unknown")
    inventors = [i.get("inventorNameText", "") for i in meta.get("inventorBag", [])]
    inventors = [i for i in inventors if i] or [meta.get("firstInventorName", "(not listed)")]
    cpc = _pick_cpc(meta.get("cpcClassificationBag", []), cpc_prefix)
    if not cpc:
        return None  # unclassified (preexam/reissue) — never guess a class
    title = meta.get("inventionTitle", "(untitled)")
    return Disclosure(
        id=f"uspto-{app_no}",
        title=title,
        inventors=inventors,
        technology_class=cpc[:4],  # section+class, e.g. "G06N"
        summary=f"{title}. USPTO application {app_no}, CPC {cpc}, "
        f"{meta.get('applicationStatusDescriptionText', '')} "
        f"(filed {meta.get('filingDate', '?')}). "
        "[real USPTO metadata; abstract not exposed by the file-wrapper endpoint]",
        details=f"CPC classifications: {', '.join(str(c).strip() for c in meta.get('cpcClassificationBag', []))}. "
        f"Art unit {meta.get('groupArtUnitNumber', '?')}, examiner {meta.get('examinerNameText', '?')}. "
        f"Application type: {meta.get('applicationTypeLabelName', '?')}.",
    )


def _map_decision(rec: dict) -> dict:
    tm = rec.get("trialMetaData", {})
    owner = rec.get("patentOwnerData", {})
    return {
        "proceeding": rec.get("trialNumber", ""),
        "document_category": rec.get("trialDocumentCategory", ""),
        "status": tm.get("trialStatusCategory", ""),
        "trial_type": tm.get("trialTypeCode", ""),
        "decision_date": tm.get("latestDecisionDate", ""),
        "application": owner.get("applicationNumberText", ""),
        "grant_date": owner.get("grantDate", ""),
        "raw": rec,  # full record kept for the distiller (the "why" is in the doc text)
    }


# ---------------------------------------------------------------------------
# Full-text documents — real invention content (E1) and real rejections (E2).
#
# The search endpoint carries metadata only; there is no abstract on it. The
# abstract, the claims, and the examiner's rejections are each a separate
# document in the file wrapper, downloadable as a tar of WIPO ST.96 XML:
#   ABST abstract · CLM claims · CTNF/CTFR office action · REM applicant remarks
# ---------------------------------------------------------------------------

DOC_TIMEOUT = 90
OA_CODES = ("CTNF", "CTFR")  # non-final / final rejection

# ST.96 text starts with the doc code, application number and page count.
_HEADER_LINE = re.compile(
    r"^(ABST|CLM|SPEC|CTNF|CTFR|REM|[\d/,\-]+|ABSTRACT OF THE DISCLOSURE|"
    r"WHAT IS CLAIMED IS:?|CLAIMS?|AMENDMENTS TO THE CLAIMS|"
    r"Application No\.[\d/,\s]*)\s*$",
    re.IGNORECASE,
)

# The heading a document's real content starts after.
_SECTION_MARKER = re.compile(
    r"^\s*(ABSTRACT(?: OF THE DISCLOSURE)?|WHAT IS CLAIMED IS:?|"
    r"(?:AMENDMENTS TO|LISTING OF) THE CLAIMS|CLAIMS)\s*$",
    re.IGNORECASE | re.MULTILINE,
)


REQUEST_SPACING = 0.4   # seconds between calls — ODP throttles aggressively
MAX_RETRIES = 5
_last_call = 0.0


def _fetch(url: str, api_key: str) -> bytes:
    """GET with polite spacing and backoff. ODP answers 429 well before any
    documented quota, and a groundtruth pull makes ~4 calls per application."""
    global _last_call
    for attempt in range(MAX_RETRIES):
        gap = time.monotonic() - _last_call
        if gap < REQUEST_SPACING:
            time.sleep(REQUEST_SPACING - gap)
        req = urllib.request.Request(url, headers={"X-API-KEY": api_key})
        try:
            with urllib.request.urlopen(req, timeout=DOC_TIMEOUT) as resp:
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


# ST.96 marks amended text with <com:Ins>/<com:Del> *mid-word*, so "Claims" is
# stored as "Claim" + <Ins>s</Ins>. Joining every text node with a newline (as
# `itertext()` invites) therefore splits words in half and no rejection regex
# matches. Concatenate these; treat every other element as a block, or
# <pat:ClaimNumber>1</> glues onto the following "1. A method..." as "11.".
# Inline = anything that can appear mid-sentence inside a <uscom:P>. Office
# actions wrap every run in <Font>, and drop the examiner's fill-ins into
# <DataField><GeneralText> — so the claim list in "Claim|s 1-5, 8 ... are|
# rejected under 35 U.S.C. 103" is itself a field split across three elements.
_INLINE_TAGS = {"ins", "del", "b", "i", "u", "s", "em", "strong", "sub", "sup",
                "strike", "underline", "superscript", "subscript", "highlight",
                "span", "boundarydatareference", "font", "datafield",
                "generaltext", "text", "emphasis", "anchor", "a"}


def _element_text(node) -> str:
    """Flatten an element, gluing inline runs and breaking on everything else."""
    parts: list[str] = []

    def walk(el) -> None:
        if el.text:
            parts.append(el.text)
        for child in el:
            walk(child)
        if el.tag.rsplit("}", 1)[-1].lower() not in _INLINE_TAGS:
            parts.append("\n")
        if el.tail:
            parts.append(el.tail)

    walk(node)
    return "".join(parts)


def _archive_text(blob: bytes) -> str:
    """`/xmlarchive` returns a tar of ST.96 XML — untar, drop tags, keep text."""
    archive = tarfile.open(fileobj=io.BytesIO(blob))
    chunks = []
    for member in archive.getmembers():
        # The tar also carries figure artwork (a nested .zip of .svg); decoding
        # that as UTF-8 dumps binary into the claim text.
        if not member.isfile() or not member.name.lower().endswith(".xml"):
            continue
        raw = archive.extractfile(member).read().decode("utf-8", "replace")
        try:
            text = _element_text(ET.fromstring(raw))
        except ET.ParseError:
            text = re.sub(r"<[^>]+>", " ", raw)  # malformed — fall back to tag-strip
        text = re.sub(r"[ \t]+", " ", text)
        chunks.append(re.sub(r"\n\s*\n\s*\n+", "\n\n", text))
    return "\n".join(chunks)


def _body(text: str) -> str:
    """Strip everything ahead of the actual content.

    Documents open with ST.96 metadata and, on filings, an attorney docket
    block ("Client Ref. No.: ... D&S Ref. No.: ..."). Both sit before the
    section heading, so when there is a heading, start after it.
    """
    marker = None
    for m in _SECTION_MARKER.finditer(text):
        marker = m
        break
    if marker:
        text = text[marker.end():]
    lines = text.split("\n")
    i = 0
    while i < len(lines) and (not lines[i].strip() or _HEADER_LINE.match(lines[i].strip())):
        i += 1
    return "\n".join(lines[i:]).strip()


def _documents(app_no: str, api_key: str) -> list[dict]:
    payload = json.loads(_fetch(f"{API}/patent/applications/{app_no}/documents", api_key))
    return payload.get("documentBag", [])


def _doc_text(docs: list[dict], codes, api_key: str) -> tuple[str, str]:
    """Text of the first document matching `codes`, plus the code it came from."""
    if isinstance(codes, str):
        codes = (codes,)
    for doc in docs:
        code = doc.get("documentCode")
        if code not in codes:
            continue
        for opt in doc.get("downloadOptionBag", []):
            if opt.get("mimeTypeIdentifier") == "XML":
                return _archive_text(_fetch(opt["downloadUrl"], api_key)), code
    return "", ""


# What the statute means when the examiner's wording doesn't narrow it further.
# §112 is deliberately absent: (a) written description/enablement and (b)
# indefiniteness are different failures, so it falls to the phrase matches.
_STATUTE_DEFAULT = {
    "§101": "abstract-idea eligibility",
    "§102": "anticipation by a single reference",
    "§103": "obviousness over prior art",
}


def _defect_pattern(category: str, rationale: str) -> str:
    """Name the failure mode from the examiner's own words."""
    low = rationale.lower()
    for phrase, name in (
        ("antecedent basis", "antecedent-basis gap"),
        ("indefinite", "indefiniteness"),
        ("written description", "written-description gap"),
        ("enablement", "enablement gap"),
        ("abstract idea", "abstract-idea eligibility"),
        ("obvious", "obviousness over combined prior art"),
        ("anticipat", "anticipation by a single reference"),
    ):
        if phrase in low:
            return f"{category} — {name}"
    fallback = _STATUTE_DEFAULT.get(category)
    return f"{category} — {fallback}" if fallback else f"{category} rejection"


_CLAIM_START = re.compile(r"^\s*(\d{1,3})\s*\.\s+", re.MULTILINE)

# The formal rejection statement, which every office action uses verbatim:
#   "Claims 1-5, 8, 10-14, 17, and 19-20 are rejected under 35 U.S.C. 103 as
#    being unpatentable over Mohammed et al (US 2025/0348732) in view of Rubin"
# Parsing this beats keying off marker words: the claim list, the statute and
# the cited art are all in one sentence, in a fixed order.
_REJECTION_STMT = re.compile(
    r"claims?\s+((?:\d+\s*[–-]\s*\d+|\d+|,|\s|\band\b)+?)\s*(?:is|are)\s+rejected\s+"
    r"under\s+35\s*U\.?\s*S\.?\s*C\.?\s*[§\s]*(\d{3})([^.]{0,300})",
    re.IGNORECASE)
RATIONALE_WINDOW = 800  # chars of examiner reasoning kept after the statement


def _parse_claims(claims_text: str) -> dict[int, str]:
    """Split a CLM document into {claim number: claim text}."""
    parts = _CLAIM_START.split(claims_text)
    out: dict[int, str] = {}
    for i in range(1, len(parts) - 1, 2):  # [pre, num, body, num, body, ...]
        num = int(parts[i])
        body = re.sub(r"\s+", " ", parts[i + 1]).strip()
        if num not in out and len(body) >= 40:
            out[num] = body
    return out


def _expand_claim_list(raw: str) -> list[int]:
    """"1-5, 8, 10-14, 17, and 19-20" -> [1,2,3,4,5,8,10,11,12,13,14,17,19,20]"""
    nums: list[int] = []
    for token in re.split(r",|\band\b", raw):
        token = token.strip()
        span = re.match(r"^(\d+)\s*[–-]\s*(\d+)$", token)
        if span and 0 <= int(span.group(2)) - int(span.group(1)) < 100:
            nums.extend(range(int(span.group(1)), int(span.group(2)) + 1))
        elif token.isdigit():
            nums.append(int(token))
    return sorted(set(nums))


def _rejections(oa_text: str) -> list[dict]:
    """Every formal rejection in an office action, with its reasoning."""
    hits = list(_REJECTION_STMT.finditer(oa_text))
    out = []
    for i, m in enumerate(hits):
        stop = hits[i + 1].start() if i + 1 < len(hits) else len(oa_text)
        window = oa_text[m.start():min(stop, m.start() + RATIONALE_WINDOW)]
        out.append({
            "claims": _expand_claim_list(m.group(1)),
            "statute": f"§{m.group(2)}",
            "cited": re.sub(r"\s+", " ", m.group(3)).strip(" .,;"),
            "rationale": re.sub(r"\s+", " ", window).strip(),
        })
    return out


def _to_loopholes(oa_text: str, claims: dict[int, str], app_no: str,
                  tech_class: str, oa_code: str) -> list[LoopholeRecord]:
    """Office action + claims -> the repo's LoopholeRecord shape.

    One record per rejected independent claim. A rejection whose claims cannot
    be matched to the CLM document is dropped rather than recorded with junk.
    """
    out = []
    seen: set[int] = set()
    for rej in _rejections(oa_text):
        numbers = [n for n in rej["claims"] if n in claims]
        if not numbers:
            continue
        lowest = numbers[0]  # lowest-numbered rejected claim — the independent one
        if lowest in seen:
            continue
        seen.add(lowest)
        digest = hashlib.sha1(f"{app_no}|{lowest}|{rej['statute']}".encode()).hexdigest()[:8]
        out.append(LoopholeRecord(
            id=f"oa-{app_no}-c{lowest}-{digest}",
            pattern=_defect_pattern(rej["statute"], rej["rationale"]),
            claim_shape=claims[lowest],
            technology_class=tech_class,
            remedy=f"Examiner's ground: {rej['rationale'][:400]}",
            source=f"USPTO application {app_no}, {oa_code} office action; "
                   f"claim{'s' if len(numbers) > 1 else ''} "
                   f"{', '.join(str(n) for n in numbers[:12])} rejected under "
                   f"35 U.S.C. {rej['statute'].lstrip('§')}"
                   + (f" {rej['cited']}" if rej["cited"] else ""),
        ))
    return out


PAGE_ROWS = 25  # ODP caps a search page at 25 however many rows you ask for


def _search_pages(query: str, key: str, max_pages: int):
    """Yield application records, paging the search endpoint past its 25 cap."""
    for page in range(max_pages):
        payload = _get("/patent/applications/search",
                       {"q": query, "rows": PAGE_ROWS, "offset": page * PAGE_ROWS}, key)
        records = payload.get("patentFileWrapperDataBag", [])
        if not records:
            return
        yield from records


def pull_groundtruth(query: str, cpc: str, limit: int, key: str) -> list[tuple[Disclosure, list[LoopholeRecord]]]:
    """Real disclosures with real claims, plus the defects examiners actually found.

    Only applications carrying an office action are kept — an allowed-first-pass
    patent teaches nothing about how claims fail. Roughly half of a page clears
    that bar, so page well past `limit`.
    """
    pairs: list[tuple[Disclosure, list[LoopholeRecord]]] = []
    pages = max(4, limit // 4 + 4)
    for rec in _search_pages(_patents_query(query, cpc), key, pages):
        if len(pairs) >= limit:
            break
        app_no = rec.get("applicationNumberText", "")
        base = _map_application(rec, cpc)
        if base is None or not app_no:
            continue
        try:
            docs = _documents(app_no, key)
            oa_text, oa_code = _doc_text(docs, OA_CODES, key)
            if not oa_text:
                continue  # never rejected — no ground truth to mine
            abstract, _ = _doc_text(docs, "ABST", key)
            claims, _ = _doc_text(docs, "CLM", key)
        except (urllib.error.URLError, tarfile.TarError, OSError, ValueError) as exc:
            print(f"  {app_no}: skipped ({type(exc).__name__}: {exc})", file=sys.stderr)
            continue

        claims_body = _body(claims)
        found = _to_loopholes(oa_text, _parse_claims(claims_body),
                              app_no, base.technology_class, oa_code)
        pairs.append((Disclosure(
            id=base.id,
            title=base.title,
            inventors=base.inventors,
            technology_class=base.technology_class,
            summary=_body(abstract) or base.summary,
            details=claims_body or base.details,
        ), found))
        print(f"  {app_no}: {oa_code}, {len(found)} defects, "
              f"abstract={'yes' if abstract else 'no'} claims={'yes' if claims else 'no'}")
    return pairs


def _patents_query(query: str, cpc: str) -> str:
    """Fielded query — the free-text form returns unclassified junk.

    Plain `q=<terms>` matches preexam/reissue/reexam wrappers that carry no CPC
    at all (and whose inventorBag holds attorneys and third-party requesters,
    not inventors). Constrain to granted, regular applications in the requested
    class so every record has real claims behind it.
    """
    parts = ['applicationMetaData.applicationStatusDescriptionText:"Patented Case"',
             'applicationMetaData.applicationTypeCategory:"REGULAR"']
    if cpc:
        parts.insert(0, f"applicationMetaData.cpcClassificationBag:{cpc}*")
    if query:
        parts.append(f"({query})")
    return " AND ".join(parts)


def pull_patents(query: str, cpc: str, limit: int, key: str) -> list[Disclosure]:
    payload = _get("/patent/applications/search",
                   {"q": _patents_query(query, cpc), "rows": limit * 4}, key)
    out = []
    for rec in payload.get("patentFileWrapperDataBag", []):
        d = _map_application(rec, cpc)
        if d is None:
            continue  # no CPC on the record — skip rather than mislabel it
        out.append(d)
        if len(out) >= limit:
            break
    return out


FWD_QUERY = 'trialMetaData.trialStatusCategory:"Final Written Decision"'


def pull_ptab(query: str, limit: int, key: str, fwd_only: bool = True) -> list[dict]:
    # Final Written Decisions adjudicate claim validity (the "which claims died"
    # ground truth). The fielded status query returns FWDs directly; AND it with
    # the caller's topical query to scope by subject.
    q = f"{FWD_QUERY} AND ({query})" if (fwd_only and query) else (FWD_QUERY if fwd_only else query)
    payload = _get("/patent/trials/decisions/search", {"q": q, "rows": limit}, key)
    return [_map_decision(r) for r in payload.get("patentTrialDocumentDataBag", [])[:limit]]


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--patents", action="store_true")
    ap.add_argument("--ptab", action="store_true")
    ap.add_argument("--groundtruth", action="store_true",
                    help="real claims + the examiner rejections against them (E1+E2)")
    ap.add_argument("--query", default="machine learning")
    ap.add_argument("--cpc", default="G06", help="CPC prefix filter for patents")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    key = os.getenv("USPTO_API_KEY")
    if not key:
        print("USPTO_API_KEY not set — register a free key at https://data.uspto.gov. "
              "No key, no pull (this script never fabricates).", file=sys.stderr)
        return 2
    if not (args.patents or args.ptab or args.groundtruth):
        print("pass --patents, --ptab and/or --groundtruth", file=sys.stderr)
        return 2

    if args.groundtruth:
        print(f"pulling {args.limit} {args.cpc}* applications that carry an office action...")
        pairs = pull_groundtruth(args.query, args.cpc, args.limit, key)
        disc_dir = DATA / "real" / "disclosures"
        chk_dir = DATA / "real" / "checklists"
        gt_dir = DATA / "real" / "groundtruth"
        for path in (disc_dir, chk_dir, gt_dir):
            path.mkdir(parents=True, exist_ok=True)

        loopholes = [lh for _, found in pairs for lh in found]
        for disclosure, found in pairs:
            (disc_dir / f"{disclosure.id}.json").write_text(
                disclosure.model_dump_json(indent=2))
            # One checklist per disclosure — the layout agent/eval/harness.py
            # loads (`load_checklist(dir, disclosure_id)`). Written only when
            # there is something to grade against: an empty checklist scores
            # 0-of-0 and would read as a passing ablation.
            if found:
                (chk_dir / f"{disclosure.id}.json").write_text(
                    json.dumps([lh.model_dump() for lh in found], indent=2))
        (gt_dir / "loopholes.json").write_text(
            json.dumps([lh.model_dump() for lh in loopholes], indent=2))

        by_cat: dict[str, int] = {}
        for lh in loopholes:
            by_cat[lh.pattern] = by_cat.get(lh.pattern, 0) + 1
        with_checklist = sum(1 for _, found in pairs if found)
        print(f"\n{len(pairs)} disclosures (real abstract + claims) -> {disc_dir}")
        print(f"{with_checklist} held-out checklists -> {chk_dir}")
        print(f"{len(loopholes)} loopholes from real office actions -> {gt_dir}/loopholes.json")
        for pat, n in sorted(by_cat.items(), key=lambda kv: -kv[1]):
            print(f"   {n:3}  {pat}")
        print("\nNote: loopholes.json pools every disclosure's defects. When warming "
              "memory for disclosure X, exclude X's own records or the harness's "
              "no-overlap guard will (correctly) trip.")

    if args.patents:
        disclosures = pull_patents(args.query, args.cpc, args.limit, key)
        out = DATA / "real" / "disclosures"
        out.mkdir(parents=True, exist_ok=True)
        for d in disclosures:
            (out / f"{d.id}.json").write_text(d.model_dump_json(indent=2))
        print(f"pulled {len(disclosures)} real disclosures ({args.cpc}*) -> {out}")

    if args.ptab:
        decisions = pull_ptab(args.query, args.limit, key)
        out = DATA / "real" / "ptab"
        out.mkdir(parents=True, exist_ok=True)
        (out / "decisions.json").write_text(json.dumps(decisions, indent=2))
        finals = sum(d["status"] == "Final Written Decision" for d in decisions)
        print(f"pulled {len(decisions)} PTAB decisions ({finals} final written) -> {out}")

    return 0


if __name__ == "__main__":
    sys.exit(main())
