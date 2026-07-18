"""Pull real USPTO data into the Airtight shapes via the ODP API.

Endpoints + field mappings VERIFIED against live responses 2026-07-18 (needs a
free key — set USPTO_API_KEY; register at https://data.uspto.gov):
  patents  GET https://api.uspto.gov/api/v1/patent/applications/search
  ptab     GET https://api.uspto.gov/api/v1/patent/trials/decisions/search

    export USPTO_API_KEY=...
    python -m data.pull_uspto --patents --query "neural network cache" --cpc G06 --limit 20
    python -m data.pull_uspto --ptab --query obviousness --limit 30

Patents -> Disclosure (real title/CPC/inventors; the file-wrapper endpoint does
not expose the abstract, so summary/details are built from real metadata and
flagged). PTAB decisions -> raw records for distill_loopholes.py (the "why" is in
the decision document text). Never fabricates: no key, no pull.
"""

import argparse
import json
import os
import sys
import urllib.parse
import urllib.request
from pathlib import Path

from airtight import Disclosure

API = "https://api.uspto.gov/api/v1"
DATA = Path(__file__).resolve().parent


def _get(path: str, params: dict, api_key: str) -> dict:
    url = f"{API}{path}?{urllib.parse.urlencode(params)}"
    req = urllib.request.Request(url, headers={"X-API-KEY": api_key})
    with urllib.request.urlopen(req, timeout=45) as resp:
        return json.loads(resp.read())


def _clean_cpc(cpc_bag: list) -> str:
    if not cpc_bag:
        return ""
    return "".join(str(cpc_bag[0]).split())  # "G06N  20/20" -> "G06N20/20"


def _map_application(rec: dict) -> Disclosure:
    meta = rec.get("applicationMetaData", {})
    app_no = rec.get("applicationNumberText", "unknown")
    inventors = [i.get("inventorNameText", "") for i in meta.get("inventorBag", [])]
    inventors = [i for i in inventors if i] or [meta.get("firstInventorName", "(not listed)")]
    cpc = _clean_cpc(meta.get("cpcClassificationBag", []))
    title = meta.get("inventionTitle", "(untitled)")
    return Disclosure(
        id=f"uspto-{app_no}",
        title=title,
        inventors=inventors,
        technology_class=cpc[:4] or "G06F",  # section+class, e.g. "G06N"
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


def pull_patents(query: str, cpc: str, limit: int, key: str) -> list[Disclosure]:
    payload = _get("/patent/applications/search", {"q": query, "rows": limit * 4}, key)
    out = []
    for rec in payload.get("patentFileWrapperDataBag", []):
        d = _map_application(rec)
        if cpc and not d.technology_class.upper().startswith(cpc.upper()):
            continue  # scope to the requested CPC prefix (software/electronics)
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
    ap.add_argument("--query", default="machine learning")
    ap.add_argument("--cpc", default="G06", help="CPC prefix filter for patents")
    ap.add_argument("--limit", type=int, default=20)
    args = ap.parse_args()

    key = os.getenv("USPTO_API_KEY")
    if not key:
        print("USPTO_API_KEY not set — register a free key at https://data.uspto.gov. "
              "No key, no pull (this script never fabricates).", file=sys.stderr)
        return 2
    if not (args.patents or args.ptab):
        print("pass --patents and/or --ptab", file=sys.stderr)
        return 2

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
