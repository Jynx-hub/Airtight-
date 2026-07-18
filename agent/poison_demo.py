"""Track-2 end-to-end demo: all FIVE HiddenLayer hops fire in one flow, and the
poisoned prior-art document is caught on ingest and quarantined.

    python -m agent.poison_demo --fake      # rehearsal, no creds / no network
    AIRTIGHT_HL_ENABLED=true python -m agent.poison_demo   # live (needs HL creds)

The flow, and the hop each step exercises:
  1. drafting request through the doorway  -> user_prompt + model_response
  2. pull the poisoned prior-art document  -> ingested_document  (CAUGHT)
  3. guarded prior-art search              -> tool_call + tool_result
At the end it prints the audit log, proving every one of the five interaction
types was analyzed — the depth Track 2 rewards.
"""

import argparse
import sys
from pathlib import Path

from airtight import call_model, config
from airtight import guardrails as g
from agent.ingest import ingest_document

POISONED = Path(__file__).resolve().parent.parent / "data" / "fixtures" / "poisoned_prior_art.txt"


@g.guarded_tool
def prior_art_search(query: str) -> str:
    """A prior-art search tool — wrapped so its call args (tool_call) and its
    result (tool_result) both cross the HiddenLayer bus."""
    return f"3 clean references for '{query}': US10111222, US10333444, EP2555666"


# --- fake mode: canned HiddenLayer responses, no network / no creds ---
_CLEAN = {"metadata": {"event_id": "fake-clean"},
          "analysis": [{"name": "prompt_injection", "phase": "input", "detected": False,
                        "findings": {"matches": []}}]}
_DETECT = {"metadata": {"event_id": "fake-detect"},
           "analysis": [{"name": "prompt_injection", "phase": "input", "detected": True,
                         "findings": {"matches": ["Ignore your instructions"]}}]}


def _install_fake():
    config.HL_ENABLED = True

    def fake(text, phase):
        return _DETECT if "Ignore your instructions" in text else _CLEAN

    g._raw_analyze = fake


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--fake", action="store_true", help="canned HL responses (no creds/network)")
    args = ap.parse_args()
    if args.fake:
        _install_fake()

    if not config.HL_ENABLED:
        print("HiddenLayer bus is OFF. Run with --fake (rehearsal) or set "
              "AIRTIGHT_HL_ENABLED=true plus HL creds for the live bus.", file=sys.stderr)
        return 2

    print("== Airtight Track-2 demo — five interaction types on the HiddenLayer bus ==\n")

    print("[1] Drafting request (fires user_prompt + model_response):")
    reply = call_model([{"role": "user", "content": "Draft a claim for a predictive cache."}],
                       role="draft", max_tokens=60)
    print(f"    model replied ({len(reply.text)} chars), both hops analyzed.\n")

    print("[2] Pull a prior-art document — the poisoned one (fires ingested_document):")
    admitted = ingest_document(POISONED)
    if admitted is None:
        print("    QUARANTINED — indirect injection caught on ingest; drafting continues clean.\n")
    else:
        print("    admitted (scan clean).\n")

    print("[3] Guarded prior-art search (fires tool_call + tool_result):")
    print(f"    {prior_art_search('predictive cache eviction')}\n")

    fired = {r["hop"] for r in g.AUDIT_LOG}
    expected = {h.value for h in g.Hop}
    print("== Hops analyzed this flow ==")
    for hop in g.Hop:
        print(f"  {'✓' if hop.value in fired else '·'} {hop.value}")
    ok = expected <= fired
    print(f"\nAll five interaction types instrumented: {ok}")
    print(f"Quarantine log: {len(g.QUARANTINE_LOG)} entry (the poisoned document).")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
