"""
scripts/build_poison.py  [E5]
==============================
Generate the booby-trapped prior-art PDF.

Outputs: data/poison/prior_art_malicious.pdf

Usage::

    python scripts/build_poison.py
    python scripts/build_poison.py --verify
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import click

sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.poison_builder import PoisonBuilder

TRIGGER_PHRASE = "CONFIDENTIAL:"


def _setup_logging(verbose: bool) -> None:
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )


@click.command()
@click.option("--verify", is_flag=True, default=False,
              help="After generation, run scanner to confirm both vectors are detectable.")
@click.option("--verbose", is_flag=True, default=False)
def main(verify, verbose):
    """[E5] Generate the booby-trapped prior-art PDF."""
    _setup_logging(verbose)

    click.echo("\nGenerating poisoned prior-art PDF...")
    pdf_path = PoisonBuilder().build()
    click.echo(f"  Written: {pdf_path}")
    click.echo(f"  Size:    {pdf_path.stat().st_size:,} bytes")

    if verify:
        click.echo("\nRunning scanner verification...")
        _run_scanner(pdf_path)


def _run_scanner(pdf_path: Path) -> None:
    """Simulate Person 4's scanner — detect both hidden vectors."""
    try:
        import pdfplumber
    except ImportError:
        click.echo("[SKIP] pdfplumber not installed. pip install pdfplumber")
        return

    click.echo(f"\n--- Scanner Report ---")
    click.echo(f"  PDF: {pdf_path.name}\n")

    found_text = False
    found_meta = False

    with pdfplumber.open(str(pdf_path)) as pdf:
        # Vector 1: text content
        all_text = ""
        for i, page in enumerate(pdf.pages):
            page_text = page.extract_text() or ""
            all_text += page_text
            if TRIGGER_PHRASE in page_text:
                click.echo(f"  [✓] VECTOR 1 DETECTED on page {i + 1}: white-on-white text layer")
                found_text = True
                break

        if not found_text:
            click.echo(f"  [✗] VECTOR 1 NOT FOUND in text content")

        # Vector 2: metadata
        meta = pdf.metadata or {}
        for field, value in meta.items():
            if value and TRIGGER_PHRASE in str(value):
                click.echo(f"  [✓] VECTOR 2 DETECTED in metadata field '{field}'")
                found_meta = True

        if not found_meta:
            click.echo(f"  [✗] VECTOR 2 NOT FOUND in metadata fields")
            click.echo(f"      Metadata: { {k: str(v)[:80] for k, v in meta.items()} }")

    click.echo(f"\n  Summary:")
    click.echo(f"    Hidden text layer : {'DETECTABLE ✓' if found_text else 'NOT FOUND ✗'}")
    click.echo(f"    Metadata injection: {'DETECTABLE ✓' if found_meta else 'NOT FOUND ✗'}")

    if found_text or found_meta:
        click.echo(f"\n  RESULT: Scanner PASSES — at least one vector is detectable.")
    else:
        click.echo(f"\n  RESULT: FAIL — neither vector detected. Re-generate and investigate.")

    click.echo(f"---\n")


if __name__ == "__main__":
    main()
