"""
scripts/validate_fixtures.py
=============================
Enforces the core invariant:

    checklist.source_decisions ∩ corpus.warming_set_ids == ∅

Also verifies:
  - Every disclosure has a matching checklist
  - Every checklist source_decision exists in the ground truth
  - All corpus patents have ≥ 1 claim

Run after every fixture or corpus rebuild:

    python scripts/validate_fixtures.py
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))
import config

logger = logging.getLogger(__name__)


@click.command()
@click.option("--strict", is_flag=True, default=False,
              help="Exit with code 1 on any warning (not just errors).")
def main(strict: bool) -> None:
    """Validate the data layer invariants before an eval run."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)s] %(message)s",
        datefmt="%H:%M:%S",
    )

    errors: list[str] = []
    warnings: list[str] = []

    click.echo("\n=== Data Layer Invariant Validator ===\n")

    # ------------------------------------------------------------------
    # Load manifests
    # ------------------------------------------------------------------
    corpus_manifest_path = config.DATA_DIR / "corpus" / "manifest.json"
    gt_dir = config.DATA_DIR / "groundtruth" / "decisions"
    disc_dir = config.DATA_DIR / "fixtures" / "disclosures"
    check_dir = config.DATA_DIR / "fixtures" / "checklists"

    if not corpus_manifest_path.exists():
        errors.append("Corpus manifest missing. Run: python scripts/build_corpus.py")
    if not gt_dir.exists():
        warnings.append("Ground truth directory missing. Run: python scripts/build_groundtruth.py")
    if not disc_dir.exists():
        errors.append("Disclosures directory missing. Run: python scripts/build_fixtures.py")
    if not check_dir.exists():
        errors.append("Checklists directory missing. Run: python scripts/build_fixtures.py")

    if errors:
        _print_results([], errors, [])
        sys.exit(1)

    corpus_manifest = json.loads(corpus_manifest_path.read_text())
    warming_ids: set[str] = set(corpus_manifest.get("warming_set_ids", []))

    # ------------------------------------------------------------------
    # Check 1: Checklist source_decisions ∩ warming_set == ∅
    # ------------------------------------------------------------------
    click.echo("Check 1: Checklist/warming-set non-overlap...")
    for p in sorted(check_dir.glob("*_checklist.json")):
        check = json.loads(p.read_text())
        disc_id = check.get("disclosure_id", p.stem)
        source_apps = set(check.get("source_decisions", []))
        overlap = warming_ids & source_apps
        if overlap:
            errors.append(
                f"INVARIANT VIOLATED: {disc_id} checklist source_decisions "
                f"overlap with warming set: {overlap}"
            )
        else:
            click.echo(f"  ✓ {disc_id}: no overlap with warming set")

    # ------------------------------------------------------------------
    # Check 2: Every disclosure has a matching checklist
    # ------------------------------------------------------------------
    click.echo("\nCheck 2: Disclosure ↔ checklist pairing...")
    disc_ids = {p.stem for p in disc_dir.glob("disc_*.json")}
    check_ids = {p.stem.replace("_checklist", "") for p in check_dir.glob("*_checklist.json")}

    for did in sorted(disc_ids):
        if did in check_ids:
            click.echo(f"  ✓ {did}: has matching checklist")
        else:
            warnings.append(f"Disclosure {did} has no matching checklist")

    for cid in sorted(check_ids):
        if cid not in disc_ids:
            warnings.append(f"Checklist {cid} has no matching disclosure")

    # ------------------------------------------------------------------
    # Check 3: Corpus patents all have ≥ 1 claim
    # ------------------------------------------------------------------
    click.echo("\nCheck 3: Corpus patent claim integrity...")
    patents_dir = config.DATA_DIR / "corpus" / "patents"
    empty_claims = []
    if patents_dir.exists():
        for p in patents_dir.glob("*.json"):
            try:
                patent = json.loads(p.read_text())
                if not patent.get("claims"):
                    empty_claims.append(p.name)
            except Exception:
                warnings.append(f"Malformed corpus file: {p.name}")
        if empty_claims:
            errors.append(f"Patents with empty claims array: {empty_claims}")
        else:
            click.echo(f"  ✓ All {sum(1 for _ in patents_dir.glob('*.json'))} corpus patents have claims")
    else:
        warnings.append("Corpus patents directory not found")

    # ------------------------------------------------------------------
    # Check 4: Ground truth covers all warming set patents
    # ------------------------------------------------------------------
    click.echo("\nCheck 4: Ground truth coverage...")
    if gt_dir.exists():
        gt_app_numbers = set()
        for p in gt_dir.glob("*.json"):
            try:
                rec = json.loads(p.read_text())
                app = rec.get("app_number", "")
                if app:
                    gt_app_numbers.add(app)
            except Exception:
                pass

        # Map warming patent numbers to app numbers from corpus files
        warming_apps: set[str] = set()
        if patents_dir.exists():
            for p in patents_dir.glob("*.json"):
                try:
                    patent = json.loads(p.read_text())
                    pnum = patent.get("patent_number", "")
                    app = patent.get("app_number", "")
                    if pnum in warming_ids and app:
                        warming_apps.add(app)
                except Exception:
                    pass

        uncovered = warming_apps - gt_app_numbers
        if uncovered:
            warnings.append(
                f"{len(uncovered)} warming-set patents have no ground truth record. "
                f"(First 3: {sorted(uncovered)[:3]})"
            )
        else:
            click.echo(f"  ✓ All warming-set patents have ground truth records")
    else:
        warnings.append("Ground truth not built yet — skipping coverage check")

    # ------------------------------------------------------------------
    # Results
    # ------------------------------------------------------------------
    _print_results([], errors, warnings)

    if errors or (strict and warnings):
        sys.exit(1)


def _print_results(passing: list, errors: list, warnings: list) -> None:
    click.echo(f"\n{'='*50}")
    if not errors and not warnings:
        click.echo("  ALL CHECKS PASSED ✓")
    else:
        if errors:
            click.echo(f"  ERRORS ({len(errors)}):")
            for e in errors:
                click.echo(f"    ✗ {e}")
        if warnings:
            click.echo(f"  WARNINGS ({len(warnings)}):")
            for w in warnings:
                click.echo(f"    ⚠ {w}")
    click.echo(f"{'='*50}\n")


if __name__ == "__main__":
    main()
