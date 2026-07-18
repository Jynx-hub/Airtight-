"""
scripts/build_corpus.py  [E1]
==============================
Fetch granted patents and write the warming corpus to data/corpus/.

Usage::

    python scripts/build_corpus.py --cpc G06F H04L --warming 50 --extended 300
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.corpus_builder import CorpusBuilder


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.command()
@click.option("--cpc", multiple=True, default=["G06F", "H04L"],
              show_default=True, help="CPC class prefix(es).")
@click.option("--warming", default=50, show_default=True,
              help="Number of patents in the warming set.")
@click.option("--extended", default=300, show_default=True,
              help="Number of additional patents in the extended corpus.")
@click.option("--verbose", is_flag=True, default=False)
def main(cpc, warming, extended, verbose):
    """[E1] Build the warming corpus of granted patents."""
    _setup_logging(verbose)
    log = logging.getLogger("build_corpus")

    click.echo(f"\nBuilding corpus: CPC={list(cpc)}  warming={warming}  extended={extended}")
    click.echo(f"Output: {config.DATA_DIR / 'corpus'}\n")

    builder = CorpusBuilder(
        cpc_classes=list(cpc),
        warming_count=warming,
        extended_count=extended,
    )
    manifest = asyncio.run(builder.build())

    click.echo(f"\n{'='*50}")
    click.echo(f"  Corpus build complete")
    click.echo(f"  Total patents  : {manifest['total_patents']}")
    click.echo(f"  Warming set    : {manifest['warming_set_count']}")
    click.echo(f"  Extended set   : {manifest['extended_set_count']}")
    click.echo(f"  Manifest       : {config.DATA_DIR / 'corpus' / 'manifest.json'}")
    click.echo(f"{'='*50}\n")


if __name__ == "__main__":
    main()
