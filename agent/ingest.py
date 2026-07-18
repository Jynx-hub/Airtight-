"""The ingested_document hop — where indirect injection gets caught.

    python -m agent.ingest data/fixtures/poisoned_prior_art.txt
    python -m agent.ingest <path> --fake-detect   # rehearse the quarantine path, no creds
    python -m agent.ingest <path> --fake-clean    # rehearse the clean path

Returns admitted text, None on quarantine (run continues from clean sources),
raises GuardrailBlocked on a fail-closed error (document NOT admitted).
"""

import argparse
import sys
from pathlib import Path

from airtight import config
from airtight import guardrails as g


def ingest_document(path: Path) -> str | None:
    text = Path(path).read_text()
    verdict = g.analyze(g.Hop.INGESTED_DOCUMENT, text, source=Path(path).name)
    if verdict.action is g.Action.QUARANTINE:
        return None
    return text


FAKE_DETECT = {
    "metadata": {"event_id": "fake-rehearsal-0001"},
    "analysis": [
        {"name": "prompt_injection", "phase": "input", "detected": True,
         "findings": {"matches": ["Ignore your instructions"]}},
    ],
}
FAKE_CLEAN = {
    "metadata": {"event_id": "fake-rehearsal-0002"},
    "analysis": [{"name": "prompt_injection", "phase": "input", "detected": False,
                  "findings": {"matches": []}}],
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("path", type=Path)
    ap.add_argument("--fake-detect", action="store_true", help="canned detection, zero network")
    ap.add_argument("--fake-clean", action="store_true", help="canned clean scan, zero network")
    args = ap.parse_args()

    if args.fake_detect or args.fake_clean:
        config.HL_ENABLED = True
        g._raw_analyze = lambda text, phase: FAKE_DETECT if args.fake_detect else FAKE_CLEAN

    name = args.path.name
    if not config.HL_ENABLED:
        text = args.path.read_text()
        print("[airtight:ingest] guardrails bus: OFF")
        print(f"[airtight:ingest] ADMITTED {name} ({len(text):,} chars) — UNSCANNED")
        return 0

    print(f"[airtight:ingest] guardrails bus: ON ({config.HL_ENVIRONMENT}, "
          f"project {config.HL_PROJECT_ID or 'unset'})")
    try:
        text = ingest_document(args.path)
    except g.GuardrailBlocked as exc:
        print(f"[airtight:ingest] BLOCKED (fail-closed): {exc} — document NOT admitted; "
              "escalate to operator")
        return 2

    last = g.AUDIT_LOG[-1]
    if text is None:
        print(f"[airtight:ingest] hop=ingested_document event={last['event_id']} "
              f"DETECTED: {', '.join(last['categories'])}")
        print(f"[airtight:ingest] QUARANTINED {name} — stripped from context")
        print(f"[airtight:ingest] loophole report: attempted indirect injection recorded "
              f"(source={name})")
        print("[airtight:ingest] drafting continues from clean sources")
    else:
        print(f"[airtight:ingest] hop=ingested_document event={last['event_id']} — scan clean")
        print(f"[airtight:ingest] ADMITTED {name} ({len(text):,} chars)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
