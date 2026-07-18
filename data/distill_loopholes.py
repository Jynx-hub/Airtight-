"""Distill real PTAB Final Written Decisions into LoopholeRecords (Person 1, E2).

Reads the FWD records pulled by pull_uspto.py and turns each real invalidation
into a loophole pattern via the model (through the doorway, so HiddenLayer sees
the hop). Grounded in real decision facts — the statutory grounds (issueTypeBag),
the outcome (documentTitleText), and the patent context — not full opinion text
and never fabricated.

    export AIRTIGHT_MODE=live AIRTIGHT_BASE_URL=<modal>/v1 AIRTIGHT_API_KEY=... AIRTIGHT_MODEL=nemotron
    python -m data.distill_loopholes --in data/real/ptab/decisions.json --out data/real/loopholes
"""

import argparse
import json
import sys
from pathlib import Path

from airtight import LoopholeRecord, call_model, config
# The prompt and parser live in agent/distill.py — the packaged home both this
# script and the ingest path can import. DISTILL_SYSTEM is unchanged by the move
# (tests/test_distill.py pins its sha256).
from agent.distill import DISTILL_SYSTEM, parse_json

GROUND = {"101": "§101 subject-matter eligibility (Alice/Mayo abstract idea)",
          "102": "§102 anticipation by prior art",
          "103": "§103 obviousness over prior art",
          "112": "§112 indefiniteness / means-plus-function / enablement"}

_parse_json = parse_json  # kept: the private name is the one this module has always used


def _tech_class(owner: dict) -> str:
    tc = str(owner.get("technologyCenterNumber", "")).strip()
    return f"TC{tc}" if tc else "TC-unknown"  # USPTO Technology Center — a real grouping


def distill_one(rec: dict) -> LoopholeRecord | None:
    raw = rec.get("raw", {})
    owner = raw.get("patentOwnerData", {})
    grounds = [GROUND.get(str(g), f"§{g}") for g in raw.get("decisionData", {}).get("issueTypeBag", [])]
    outcome = raw.get("documentData", {}).get("documentTitleText", "claims held unpatentable")

    user = (
        f"PROCEEDING: {rec.get('proceeding')}\n"
        f"PATENT: {owner.get('patentNumber', '?')} (art unit {owner.get('groupArtUnitNumber', '?')}, "
        f"tech center {owner.get('technologyCenterNumber', '?')})\n"
        f"OUTCOME: {outcome}\n"
        f"STATUTORY GROUNDS THE CLAIMS DIED ON: {', '.join(grounds) or 'not specified'}"
    )
    reply = call_model(
        [{"role": "system", "content": DISTILL_SYSTEM}, {"role": "user", "content": user}],
        role="tool", max_tokens=400,
    )
    data = _parse_json(reply.text) or {}
    if not data.get("pattern"):
        return None
    stub = reply.mode == "stub"
    return LoopholeRecord(
        id=f"ptab-{rec.get('proceeding', 'unknown')}",
        pattern=data["pattern"][:200],
        claim_shape=data.get("claim_shape", "")[:300],
        technology_class=_tech_class(owner),
        remedy=data.get("remedy", "")[:300],
        source=f"PTAB {rec.get('proceeding')} FWD, patent {owner.get('patentNumber', '?')}, "
        f"grounds {raw.get('decisionData', {}).get('issueTypeBag', [])}"
        + ("  [STUB — not real]" if stub else ""),
    )


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--in", dest="infile", type=Path, default=Path("data/real/ptab/decisions.json"))
    ap.add_argument("--out", type=Path, default=Path("data/real/loopholes"))
    args = ap.parse_args()

    if config.MODE == "stub":
        print("WARNING: stub mode — output is placeholder, not real ground truth.", file=sys.stderr)

    decisions = json.loads(args.infile.read_text())
    args.out.mkdir(parents=True, exist_ok=True)
    written = 0
    for i, rec in enumerate(decisions):
        try:
            record = distill_one(rec)
        except Exception as exc:
            print(f"  [{i}] {rec.get('proceeding')}: {type(exc).__name__}: {exc}", file=sys.stderr)
            continue
        if record:
            (args.out / f"{record.id}.json").write_text(record.model_dump_json(indent=2))
            written += 1
            print(f"  [{i}] {record.id}: {record.pattern[:70]}")
    print(f"\ndistilled {written}/{len(decisions)} FWDs -> {args.out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
