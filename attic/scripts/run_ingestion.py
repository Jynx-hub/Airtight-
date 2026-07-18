"""
scripts/run_ingestion.py
=========================
CLI entry point for the patent defect ingestion pipeline.

Examples::

    # Dry-run smoke test (100 records, no DB writes)
    python scripts/run_ingestion.py --cpc G06F --limit 100 --dry-run

    # Full ingestion for all 4 CPC classes
    python scripts/run_ingestion.py --cpc G06F H04L H01L G06N --limit 15000 --workers 8

    # Resume after interruption
    python scripts/run_ingestion.py --cpc G06F H04L H01L G06N --limit 15000 --resume

    # Query the results
    python scripts/run_ingestion.py --query
"""

from __future__ import annotations

import asyncio
import logging
import sys
from pathlib import Path

import click

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
import config
from src.pipeline import IngestionPipeline, PipelineConfig
from src.db import PatentDB

# ---------------------------------------------------------------------------
# Logging setup
# ---------------------------------------------------------------------------

def _setup_logging(verbose: bool) -> None:
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )
    # Silence noisy third-party loggers
    logging.getLogger("aiohttp").setLevel(logging.WARNING)
    logging.getLogger("asyncio").setLevel(logging.WARNING)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

@click.command()
@click.option(
    "--cpc",
    multiple=True,
    default=config.CPC_CLASSES,
    show_default=True,
    help="CPC class prefix(es) to target. Repeat for multiple.",
)
@click.option(
    "--limit",
    default=config.DEFAULT_LIMIT_PER_CLASS,
    show_default=True,
    help="Max records to fetch per CPC class.",
)
@click.option(
    "--workers",
    default=8,
    show_default=True,
    help="Number of concurrent API workers (max 20).",
)
@click.option(
    "--dry-run",
    is_flag=True,
    default=False,
    help="Fetch and extract but do not write to DB.",
)
@click.option(
    "--resume",
    is_flag=True,
    default=False,
    help="Resume from checkpoint (skip already-ingested apps).",
)
@click.option(
    "--source",
    default="peds",
    type=click.Choice(["peds", "patentsview", "both"]),
    show_default=True,
    help="Data source to use.",
)
@click.option(
    "--db",
    "db_path",
    default=str(config.DB_PATH),
    show_default=True,
    help="Path to DuckDB output file.",
)
@click.option(
    "--query",
    is_flag=True,
    default=False,
    help="Print a summary of the current DB contents and exit.",
)
@click.option(
    "--verbose",
    is_flag=True,
    default=False,
    help="Print per-record extraction details.",
)
def main(
    cpc: tuple[str, ...],
    limit: int,
    workers: int,
    dry_run: bool,
    resume: bool,
    source: str,
    db_path: str,
    query: bool,
    verbose: bool,
) -> None:
    """Patent Defect Database — ingestion pipeline CLI."""
    _setup_logging(verbose)
    log = logging.getLogger("run_ingestion")

    if query:
        asyncio.run(_print_summary(Path(db_path)))
        return

    workers = min(max(workers, 1), 20)
    cpc_list = list(cpc) if cpc else config.CPC_CLASSES

    click.echo(f"\n{'='*60}")
    click.echo(f"  Patent Defect Database — Ingestion")
    click.echo(f"{'='*60}")
    click.echo(f"  CPC classes : {', '.join(cpc_list)}")
    click.echo(f"  Limit/class : {limit:,}")
    click.echo(f"  Workers     : {workers}")
    click.echo(f"  Source      : {source}")
    click.echo(f"  Dry run     : {dry_run}")
    click.echo(f"  Resume      : {resume}")
    click.echo(f"  Database    : {db_path}")
    click.echo(f"{'='*60}\n")

    cfg = PipelineConfig(
        cpc_classes=cpc_list,
        limit_per_class=limit,
        workers=workers,
        dry_run=dry_run,
        resume=resume,
        source=source,
        db_path=Path(db_path),
        verbose=verbose,
    )

    asyncio.run(_run(cfg, log))


async def _run(cfg: PipelineConfig, log: logging.Logger) -> None:
    async with IngestionPipeline(cfg) as pipeline:
        stats = await pipeline.run()

    click.echo(f"\n{'='*60}")
    click.echo(f"  Ingestion complete")
    click.echo(f"{'='*60}")
    click.echo(f"  Applications fetched : {stats.fetched:,}")
    click.echo(f"  Defects extracted    : {stats.extracted:,}")
    click.echo(f"  Records inserted     : {stats.inserted:,}")
    click.echo(f"  Skipped (checkpoint) : {stats.skipped:,}")
    click.echo(f"  Errors               : {stats.errors:,}")
    click.echo(f"  Elapsed              : {stats.elapsed()}")

    if not cfg.dry_run:
        click.echo(f"\n  DB: {cfg.db_path}")
        click.echo(f"  Query: duckdb {cfg.db_path} \"SELECT * FROM defect_summary\"")
    click.echo("")


async def _print_summary(db_path: Path) -> None:
    """Print a summary of the DB contents."""
    if not db_path.exists():
        click.echo(f"No database found at {db_path}")
        return

    async with PatentDB(db_path) as db:
        total = await db.count()
        by_cpc = await db.count_by_cpc()
        summary = await db.summary()

    click.echo(f"\nTotal records: {total:,}\n")
    click.echo(f"{'CPC':<8} {'Count':>8}")
    click.echo("-" * 18)
    for cpc, n in sorted(by_cpc.items()):
        click.echo(f"{cpc:<8} {n:>8,}")

    if summary:
        click.echo(f"\n{'CPC':<8} {'Defect':<8} {'Count':>8} {'w/Amendment':>12} {'Confidence':>12}")
        click.echo("-" * 55)
        for row in summary:
            click.echo(
                f"{row['cpc_class']:<8} {row['statutory_defect_category']:<8} "
                f"{row['record_count']:>8,} {row['with_amendment']:>12,} "
                f"{row['avg_confidence']:>12.2f}"
            )
    click.echo("")


if __name__ == "__main__":
    main()
