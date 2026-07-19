"""Seed the agent-generated memory stores by actually running them.

`memory/episodes/**/*.json` and `memory/ingested/*.json` are gitignored — they
are agent-generated, not corpus — so a fresh clone and every demo machine starts
at zero and has to seed its own.

    .venv/bin/python scripts/seed_memory.py --n 5

Everything here is produced by running the real path. Nothing is hand-authored.
A fabricated record would render on the engine panel as learning that never
happened, which is the one thing the surface's seam rule exists to prevent.

What each store can honestly hold offline differs, and the difference is the
whole point:

* **Episodes** — real runs, real files, but in stub mode the critique turn returns
  canned text naming no defect, so `material_defects` is empty and NOTHING NEW is
  distilled. The panel says so ("NOTHING LEARNED YET").
* **Lessons** — NOT seedable offline, by design. A lesson is minted from a critique
  naming a defect. The stub reply deliberately carries no defect keyword, because
  that is what keeps stub at 0 revise rounds and holds the ablation's stub-delta-0
  invariant (docs/WORKSTREAMS.md B1). Making the stub name a defect to fill a stat
  tile would trade a load-bearing eval invariant for a demo number. Run this with
  `AIRTIGHT_MODE=live` against the served model instead — the path is identical.
* **Ingested records** — fully real offline. `STUB_REPLIES["distill"]` is
  record-shaped on purpose so the parse + validate route runs for free, and the
  quarantine gate in front of it is real whenever the bus is on.

Episodes deliberately skip `jobs.draft_guardrails`, so no live USPTO prior art is
fetched or distilled into memory (B4's caveat in docs/WORKSTREAMS.md).
"""

import argparse
import pathlib
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))

from airtight import Disclosure, config  # noqa: E402
from agent.loop import draft_patent  # noqa: E402

DISCLOSURES = ROOT / "data" / "real" / "disclosures"
FIXTURES = ROOT / "data" / "fixtures"

# The clean document mints a record; the poisoned one must be stopped upstream of
# the model. Seeding both is what makes the ingested store evidence rather than a
# row count — an ingest store with no quarantine beside it proves only that
# writing works, not that gating does.
DOCUMENTS = [
    (FIXTURES / "prior_art_clean.txt", "admit"),
    (FIXTURES / "poisoned_prior_art.txt", "quarantine"),
]


def seed_episodes(n: int) -> None:
    from surface import jobs, sources

    if not config.EPISODES_ENABLED:
        print("  SKIPPED — AIRTIGHT_EPISODES_ENABLED is false, so draft_patent discards "
              "every episode.\n  Set it true in .env, or this costs time and writes nothing.")
        return

    paths = sorted(DISCLOSURES.glob("*.json"))[:n]
    if not paths:
        print(f"  SKIPPED — no disclosures in {DISCLOSURES}; run data/pull_uspto.py first")
        return

    for path in paths:
        disclosure = Disclosure.model_validate_json(path.read_text())
        # retrieve_for only — no draft_guardrails, so no prior-art fetch (see module docstring)
        guardrails, _ = jobs.retrieve_for(disclosure, k=5)
        draft = draft_patent(disclosure, guardrails=guardrails,
                             episode_sink=sources.episode_sink())
        print(f"  {disclosure.id}  retrieved {len(guardrails)}  claims {len(draft.claims)}")


def seed_ingested() -> None:
    """Run the real ingest path over the fixture documents.

    Does NOT fall back to `--fake-clean` when the bus is off. A rehearsal writes
    `fake-rehearsal-0001` into the security log, and a seeded store whose gate was
    faked is indistinguishable on disk from one whose gate really fired — the same
    class of overclaim this script exists to avoid. Better to write nothing and
    say why.
    """
    from agent.ingest import UnscannedIngest, ingest_to_memory
    from agent.memory import LoopholeStore

    if not config.HL_ENABLED:
        print("  SKIPPED — guardrails bus is OFF, so nothing can be quarantined and "
              "`ingest_to_memory` refuses to write.\n  Set AIRTIGHT_HL_ENABLED=true with "
              "credentials (real scans), or rehearse the beat with\n"
              "  `python -m agent.ingest <path> --fake-clean --remember`.")
        return

    store = LoopholeStore.load(config.INGESTED_DIR)
    print(f"  bus ON ({config.HL_ENVIRONMENT}) — these are real AIDR round-trips")

    for path, expected in DOCUMENTS:
        if not path.exists():
            print(f"  {path.name}: MISSING — skipped")
            continue
        try:
            records = ingest_to_memory(path, tech_class="G06F", store=store)
        except UnscannedIngest as exc:
            print(f"  {path.name}: REFUSED — {exc}")
            continue

        got = "admit" if records else "quarantine"
        print(f"  {path.name}: {got.upper()} — {len(records)} record(s) minted")
        if got != expected:
            # Loud on purpose. A poisoned fixture that got admitted is a live
            # security finding, not a seeding hiccup: it means attacker-controlled
            # text reached the model and the store.
            print(f"    ⚠️  EXPECTED {expected.upper()}. The gate did not behave as "
                  f"specified for a known fixture — investigate before demoing this.")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=5, help="how many disclosures to draft")
    ap.add_argument("--only", choices=["episodes", "ingested"], help="seed just one store")
    args = ap.parse_args()

    from surface import sources

    print(f"mode={config.MODE}  hl={config.HL_ENABLED}  episodes={config.EPISODES_ENABLED}")
    print(f"starting from: {len(sources.episode_store())} episode(s), "
          f"{len(sources.corpus_store())} retrievable record(s)\n")

    if args.only != "ingested":
        print("episodes:")
        seed_episodes(args.n)
    if args.only != "episodes":
        print("\ningested:")
        seed_ingested()

    store = sources.episode_store()
    # Same provenance rule the panel uses, so the two can never disagree: a
    # lesson is what compress_run MINTED, not everything the episode carried.
    minted = [r for ep in store.episodes for r in ep.distilled
              if (r.source or "").startswith("episode:")]
    ingested, _ = sources._load_store(ROOT / config.INGESTED_DIR)
    print(f"\n{'':-<60}")
    print(f"episodes        {len(store)}")
    print(f"lessons         {len(minted)}   (minted by compress_run, not copies)")
    print(f"ingested        {len(ingested)}")
    if not minted and len(store):
        print("\nlessons 0 is correct, not a failure: in stub mode the critique turn returns\n"
              "canned text naming no defect, so there is nothing to distil. The compounding\n"
              "mechanism ran; nothing was learned. AIRTIGHT_MODE=live is what fills it.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
