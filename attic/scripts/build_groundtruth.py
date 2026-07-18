"""
scripts/build_groundtruth.py  [E2]
===================================
Build the per-patent ground-truth scoring key from PTAB + PEDS data.

Usage::

    python scripts/build_groundtruth.py
    python scripts/build_groundtruth.py --patent US10123456B2 --app 16/123456 --cpc G06F
"""

from __future__ import annotations

import asyncio
import json
import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.extractors.groundtruth_builder import GroundTruthBuilder


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.command()
@click.option("--patent", default=None,
              help="Single patent number to process (skips corpus manifest).")
@click.option("--app", default=None, help="Application number (used with --patent).")
@click.option("--cpc", default="G06F", show_default=True,
              help="CPC class (used with --patent).")
@click.option("--verbose", is_flag=True, default=False)
def main(patent, app, cpc, verbose):
    """[E2] Build ground-truth scoring key from PTAB + PEDS data."""
    _setup_logging(verbose)

    builder = GroundTruthBuilder()

    if patent:
        # Single patent mode
        click.echo(f"\nBuilding ground truth for: {patent}")
        result = asyncio.run(
            builder.build_one_by_patent_number(patent, app or "", cpc)
        )
        click.echo(f"  Claim rejections : {len(result.get('claim_rejections', []))}")
        click.echo(f"  PTAB decisions   : {len(result.get('ptab_decisions', []))}")
        click.echo(f"  Dead claims      : {result.get('dead_claims', [])}")
        click.echo(f"  Surviving claims : {result.get('surviving_claims', [])}")
    else:
        # Full corpus mode
        manifest_path = config.DATA_DIR / "corpus" / "manifest.json"
        if not manifest_path.exists():
            click.echo(f"ERROR: No corpus manifest found at {manifest_path}")
            click.echo("Run: python scripts/build_corpus.py first.")
            sys.exit(1)

        manifest = json.loads(manifest_path.read_text())
        click.echo(f"\nBuilding ground truth for {manifest['total_patents']} patents...")
        click.echo(f"Output: {config.DATA_DIR / 'groundtruth'}\n")

        gt_manifest = asyncio.run(builder.build_from_corpus(manifest))

        click.echo(f"\n{'='*50}")
        click.echo(f"  Ground truth build complete")
        click.echo(f"  Total records    : {gt_manifest['total_records']}")
        click.echo(f"  Has PTAB data    : {gt_manifest['coverage']['has_ptab']}")
        click.echo(f"  Has OA data      : {gt_manifest['coverage']['has_oa_rejections']}")
        click.echo(f"  Has both         : {gt_manifest['coverage']['has_both']}")
        click.echo(f"{'='*50}\n")


if __name__ == "__main__":
    main()
