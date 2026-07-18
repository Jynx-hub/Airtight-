"""
scripts/build_fixtures.py  [E3]
================================
Write the fixed evaluation disclosures and checklists.

Usage::

    python scripts/build_fixtures.py
    python scripts/build_fixtures.py --skip-overlap-check
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.fixture_builder import FixtureBuilder


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.command()
@click.option("--skip-overlap-check", is_flag=True, default=False,
              help="Skip the warming-set overlap invariant check (unsafe).")
@click.option("--verbose", is_flag=True, default=False)
def main(skip_overlap_check, verbose):
    """[E3] Build fixed eval disclosures and held-out checklists."""
    _setup_logging(verbose)

    click.echo(f"\nBuilding eval fixtures...")
    click.echo(f"  Disclosures → {config.DATA_DIR / 'fixtures' / 'disclosures'}")
    click.echo(f"  Checklists  → {config.DATA_DIR / 'fixtures' / 'checklists'}\n")

    builder = FixtureBuilder()

    corpus_manifest = None
    if not skip_overlap_check:
        manifest_path = config.DATA_DIR / "corpus" / "manifest.json"
        if manifest_path.exists():
            corpus_manifest = json.loads(manifest_path.read_text())
            click.echo(f"  Checking overlap against warming set ({corpus_manifest.get('warming_set_count', 0)} patents)...")
        else:
            click.echo("  [WARN] No corpus manifest found — skipping overlap check.")
            click.echo("  Build corpus first with: python scripts/build_corpus.py")

    summary = builder.build(corpus_manifest=corpus_manifest)

    click.echo(f"\n{'='*50}")
    click.echo(f"  Fixture build complete")
    click.echo(f"  Disclosures : {summary['disclosures']}")
    click.echo(f"  Checklists  : {summary['checklists']}")
    click.echo(f"  IDs         : {summary['disclosure_ids']}")
    click.echo(f"  Invariant   : {summary['invariant']}")
    click.echo(f"{'='*50}\n")


if __name__ == "__main__":
    main()
