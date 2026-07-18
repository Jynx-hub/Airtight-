"""The ingested_document hop — where indirect injection gets caught.

    python -m agent.ingest data/fixtures/poisoned_prior_art.txt
    python -m agent.ingest <path> --fake-detect   # rehearse the quarantine path, no creds
    python -m agent.ingest <path> --fake-clean    # rehearse the clean path

Returns admitted text, None on quarantine (run continues from clean sources),
raises GuardrailBlocked on a fail-closed error (document NOT admitted).
"""

import argparse
import hashlib
import sys
from pathlib import Path

from airtight import LoopholeRecord, call_model, config
from airtight import guardrails as g
from agent.memory import LoopholeStore

INGESTED_DIR = "memory/ingested"  # agent-generated store, outside data/ (like memory/episodes)


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
    return text


def distill_text(text: str, source: str, tech_class: str = "TC-unknown") -> list[LoopholeRecord]:
    """D1: turn admitted document text into LoopholeRecords via the model — through the
    doorway, so HiddenLayer sees this hop too. Reuses DISTILL_SYSTEM/_parse_json (which
    already emit exactly {pattern, claim_shape, remedy}); returns 0 or 1 record."""
    from data.distill_loopholes import DISTILL_SYSTEM, _parse_json

    reply = call_model(
        [{"role": "system", "content": DISTILL_SYSTEM}, {"role": "user", "content": text[:6000]}],
        role="tool", max_tokens=400,
    )
    data = _parse_json(reply.text) or {}
    if not data.get("pattern"):
        return []
    rid = f"ingested-{hashlib.sha1(source.encode()).hexdigest()[:8]}"
    return [LoopholeRecord(
        id=rid,
        pattern=data["pattern"][:200],
        claim_shape=data.get("claim_shape", "")[:300],
        technology_class=tech_class,
        remedy=data.get("remedy", "")[:300],
        source=f"ingested:{source}" + ("  [STUB — not real]" if reply.mode == "stub" else ""),
    )]


def ingest_to_memory(path, tech_class: str = "TC-unknown",
                     memory_dir: str | Path = INGESTED_DIR) -> list[LoopholeRecord]:
    """D2 + D3: ingest a document and, ONLY if it clears the HiddenLayer gate, distill it
    into records and persist them to the ingested store.

    D3 — the story: a QUARANTINED document (indirect injection) returns None from
    ingest_document, so we write **zero** records; a fail-closed error raises before we ever
    reach distillation. Wiring ingest into memory without this gate would let an attacker
    write straight into the agent's long-term store — a persistent, compounding injection.
    The gate is what makes learning-from-untrusted-documents safe."""
    # FAIL-CLOSED: with the bus OFF, g.analyze() short-circuits to PASS (unscanned), so a
    # poisoned document would sail into long-term memory. A memory write is exactly the hop
    # that must never happen unscanned — refuse it rather than admit blind.
    if not config.HL_ENABLED:
        raise RuntimeError(
            "refusing to write ingested records to memory with the guardrail bus OFF "
            "(AIRTIGHT_HL_ENABLED=false). The HiddenLayer scan on the ingested_document hop is "
            "what keeps a poisoned document out of long-term memory; an unscanned write is the "
            "attack surface D3 exists to close. Enable the bus, or read-only via ingest_document()."
        )
    text = ingest_document(Path(path))
    if text is None:
        return []  # D3: quarantined → nothing reaches memory
    records = distill_text(text, source=Path(path).name, tech_class=tech_class)
    if records:
        store = LoopholeStore.load(memory_dir) if Path(memory_dir).exists() else LoopholeStore([])
        store.add_all(records)  # dedup by id (C3)
        store.save(memory_dir)
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
    args = ap.parse_args()

    if args.fake_detect or args.fake_clean:
        config.HL_ENABLED = True
        g._raw_analyze = lambda text, phase: FAKE_DETECT if args.fake_detect else FAKE_CLEAN

    name = args.path.name
    if not config.HL_ENABLED:
        text = _extract_text(args.path)
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
