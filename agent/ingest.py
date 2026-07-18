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

from airtight import LoopholeRecord, config
from airtight import guardrails as g


def _extract_text(path: Path) -> str:
    """Read a source document as text for the scanner.

    A PDF is flattened — every page's text plus all metadata values — so
    hidden layers reach the guardrail: white-on-white text lives in the
    content stream (`extract_text` surfaces it regardless of colour) and the
    leak phrase is also stashed in XMP fields (`pdf.metadata`). Everything
    else is read as UTF-8; a raw `.read_text()` on a binary PDF would only
    raise `UnicodeDecodeError` and never see either vector.
    """
    if path.suffix.lower() == ".pdf":
        try:
            import pdfplumber
        except ImportError:
            raise ImportError(
                "pdfplumber is required to ingest a .pdf. "
                "Install with: pip install -e \".[poison]\""
            )
        with pdfplumber.open(path) as pdf:
            pages = "\n".join(page.extract_text() or "" for page in pdf.pages)
            meta = "\n".join(str(v) for v in (pdf.metadata or {}).values())
        return f"{pages}\n{meta}"
    return path.read_text()


def ingest_document(path: Path) -> str | None:
    text = _extract_text(Path(path))
    verdict = g.analyze(g.Hop.INGESTED_DOCUMENT, text, source=Path(path).name)
    if verdict.action is g.Action.QUARANTINE:
        return None
    # verdict.text, not text: identical today (this hop maps no category to
    # REDACT, so PASS returns the input unchanged), but now that admitted text
    # can be written into long-term memory, returning the raw input would
    # persist un-redacted content the moment anyone adds a REDACT rule here.
    return verdict.text


class UnscannedIngest(RuntimeError):
    """Raised when a write into memory was requested with the scanner switched off."""


def ingest_to_memory(path: Path, *, tech_class: str, store) -> list[LoopholeRecord]:
    """Read a document and distill what it teaches into the loophole store.

    Two gates, and both must hold before anything is written:

    1. The bus must be ON. `config.HL_ENABLED` defaults to false, and
       `g.analyze` short-circuits to PASS when it is — so without this check the
       *default* configuration would distil and persist an unscanned document,
       and the quarantine gate below would never fire. Refusing is the only
       honest option: "quarantined content never reaches the store" cannot be
       true if nothing is ever classified as quarantined.
    2. The document must not be quarantined. That gate is the `None` return,
       and it sits upstream of the model — so a poisoned document doesn't merely
       fail to be written, it never reaches the model at all. No tokens are spent
       on attacker-controlled content and the doorway never sees it.

    GuardrailBlocked (the fail-closed path, when the scanner itself errors)
    deliberately propagates: it must reach the operator, and an except clause
    here would be exactly the bug that reopens the hole.
    """
    if not config.HL_ENABLED:
        raise UnscannedIngest(
            "refusing to write to memory with the guardrails bus OFF — an unscanned "
            "document cannot be quarantined, so nothing would gate it. Set "
            "AIRTIGHT_HL_ENABLED=true with credentials, or rehearse with "
            "--fake-clean / --fake-detect."
        )

    text = ingest_document(path)
    if text is None:
        return []  # quarantined — nothing distilled, nothing written

    from agent.distill import distill_text  # local: keeps the CLI import-light

    records = distill_text(text, source=Path(path).name, tech_class=tech_class)
    for rec in records:
        # add() returns False when the id is already held. save() must respect
        # that, or the newcomer silently overwrites the incumbent on disk while
        # memory keeps the original — the two would disagree after a reload.
        if store.add(rec):
            store.save(rec)
    return records


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
    # Opt-in for the same reason episode_sink defaults to None: otherwise every
    # rehearsal of the quarantine beat would mutate long-term memory.
    ap.add_argument("--remember", action="store_true",
                    help="distill admitted text into the loophole store (quarantined text never is)")
    ap.add_argument("--tech-class", default="G06F", help="CPC class for the minted record, e.g. G06F")
    ap.add_argument("--memory-dir", type=Path, default=None,
                    help=f"where records land (default: {config.INGESTED_DIR})")
    args = ap.parse_args()

    if args.fake_detect or args.fake_clean:
        config.HL_ENABLED = True
        g._raw_analyze = lambda text, phase: FAKE_DETECT if args.fake_detect else FAKE_CLEAN

    name = args.path.name
    if not config.HL_ENABLED:
        text = _extract_text(args.path)
        print("[airtight:ingest] guardrails bus: OFF")
        print(f"[airtight:ingest] ADMITTED {name} ({len(text):,} chars) — UNSCANNED")
        if args.remember:
            # Say so and fail. Returning 0 here would report success while
            # writing nothing, and writing anyway would put unscanned content
            # into long-term memory with no gate in front of it.
            print("[airtight:ingest] REFUSED --remember: nothing was scanned, so nothing "
                  "could be quarantined. Set AIRTIGHT_HL_ENABLED=true with credentials, "
                  "or rehearse with --fake-clean / --fake-detect.")
            return 2
        return 0

    print(f"[airtight:ingest] guardrails bus: ON ({config.HL_ENVIRONMENT}, "
          f"project {config.HL_PROJECT_ID or 'unset'})")

    records: list[LoopholeRecord] = []
    try:
        if args.remember:
            from agent.memory import LoopholeStore

            store = LoopholeStore.load(args.memory_dir or config.INGESTED_DIR)
            records = ingest_to_memory(args.path, tech_class=args.tech_class, store=store)
        else:
            ingest_document(args.path)
    except g.GuardrailBlocked as exc:
        print(f"[airtight:ingest] BLOCKED (fail-closed): {exc} — document NOT admitted; "
              "escalate to operator")
        return 2

    # The ingest verdict specifically, not AUDIT_LOG[-1]: with --remember the
    # distill call fires user_prompt/model_response hops afterwards, so the last
    # entry is no longer this document's scan.
    last = next(r for r in reversed(g.AUDIT_LOG) if r["hop"] == g.Hop.INGESTED_DOCUMENT.value)
    quarantined = last["action"] == "quarantine"
    if quarantined:
        print(f"[airtight:ingest] hop=ingested_document event={last['event_id']} "
              f"DETECTED: {', '.join(last['categories'])}")
        print(f"[airtight:ingest] QUARANTINED {name} — stripped from context")
        # This used to claim a recording that never happened. It does now:
        # guardrails._persist appends every quarantine verdict to the JSONL.
        print(f"[airtight:ingest] loophole report: quarantine recorded "
              f"(source={name}, event={last['event_id']}) -> results/security/quarantine.jsonl")
        print("[airtight:ingest] drafting continues from clean sources")
    else:
        print(f"[airtight:ingest] hop=ingested_document event={last['event_id']} — scan clean")
        print(f"[airtight:ingest] ADMITTED {name}")

    if args.remember:
        where = args.memory_dir or config.INGESTED_DIR
        if quarantined:
            print("[airtight:ingest] memory: 0 records written — "
                  "quarantined content never reaches the store")
        else:
            for rec in records:
                print(f"[airtight:ingest] memory: {rec.id} -> {where}/  "
                      f"(statute §{rec.statute or '?'}, confidence {rec.extraction_confidence})")
            if not records:
                print("[airtight:ingest] memory: 0 records written — "
                      "nothing distillable in the admitted text")
    return 0


if __name__ == "__main__":
    sys.exit(main())
