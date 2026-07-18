"""
src/loaders.py  [E4]
=====================
Person-4-facing loader API.

One call each — that's the contract.

Usage::

    from src.loaders import load_corpus, load_groundtruth, load_fixtures
    from src.loaders import load_checklists, load_poison

    corpus     = load_corpus()       # list[dict]
    gt         = load_groundtruth()  # dict[str, dict] keyed by app_number
    fixtures   = load_fixtures()     # list[dict] — disclosures only
    checklists = load_checklists()   # list[dict] — checklists only (graders)
    pdf_path   = load_poison()       # pathlib.Path
"""

from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

# Default data directories (all relative to config.DATA_DIR)
_CORPUS_DIR    = config.DATA_DIR / "corpus"
_GT_DIR        = config.DATA_DIR / "groundtruth"
_FIXTURES_DIR  = config.DATA_DIR / "fixtures"
_POISON_DIR    = config.DATA_DIR / "poison"


# ---------------------------------------------------------------------------
# E1 — Corpus
# ---------------------------------------------------------------------------

def load_corpus(
    data_dir: Optional[Path] = None,
    warming_only: bool = False,
) -> list[dict]:
    """
    Load the full warming corpus of granted patents.

    Args:
        data_dir:    Override the default data/corpus directory.
        warming_only: If True, return only the warming set (50 patents).
                      If False (default), return all patents.

    Returns:
        list[dict] — one dict per patent, each matching the corpus shape
        defined in docs/ARCHITECTURE.md § E1.

    Raises:
        FileNotFoundError: If the corpus directory or manifest is missing.
        ValueError: If any patent file is missing required 'claims' array.
    """
    corpus_dir = (data_dir or _CORPUS_DIR)
    manifest_path = corpus_dir / "manifest.json"

    if not manifest_path.exists():
        raise FileNotFoundError(
            f"Corpus manifest not found at {manifest_path}. "
            f"Run: python scripts/build_corpus.py"
        )

    manifest = json.loads(manifest_path.read_text())

    if warming_only:
        target_ids = set(manifest.get("warming_set_ids", []))
    else:
        target_ids = set(
            manifest.get("warming_set_ids", []) +
            manifest.get("extended_set_ids", [])
        )

    patents_dir = corpus_dir / "patents"
    patents: list[dict] = []

    for p in sorted(patents_dir.glob("*.json")):
        try:
            patent = json.loads(p.read_text())
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed patent file %s: %s", p.name, exc)
            continue

        pnum = patent.get("patent_number", "")
        if target_ids and pnum not in target_ids:
            continue

        # Validate required field
        if not patent.get("claims"):
            raise ValueError(
                f"Patent {p.name} has empty 'claims' array. "
                f"Corpus integrity check failed."
            )

        patents.append(patent)

    logger.info("load_corpus: loaded %d patents (warming_only=%s)", len(patents), warming_only)
    return patents


# ---------------------------------------------------------------------------
# E2 — Ground Truth
# ---------------------------------------------------------------------------

def load_groundtruth(
    data_dir: Optional[Path] = None,
    warn_on_gaps: bool = True,
) -> dict[str, dict]:
    """
    Load the ground-truth scoring key.

    Args:
        data_dir:     Override the default data/groundtruth directory.
        warn_on_gaps: If True, log a warning for corpus patents with no
                      corresponding ground truth record.

    Returns:
        dict[str, dict] — keyed by app_number. Values match the ground
        truth shape in docs/ARCHITECTURE.md § E2.
    """
    gt_dir = (data_dir or _GT_DIR) / "decisions"

    if not gt_dir.exists():
        raise FileNotFoundError(
            f"Ground truth directory not found at {gt_dir}. "
            f"Run: python scripts/build_groundtruth.py"
        )

    gt: dict[str, dict] = {}
    for p in sorted(gt_dir.glob("*.json")):
        try:
            record = json.loads(p.read_text())
            app = record.get("app_number", "")
            if app:
                gt[app] = record
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed GT file %s: %s", p.name, exc)

    if warn_on_gaps:
        _warn_groundtruth_gaps(gt)

    logger.info("load_groundtruth: loaded %d records", len(gt))
    return gt


def _warn_groundtruth_gaps(gt: dict) -> None:
    """Log a warning if corpus patents lack ground truth coverage."""
    corpus_manifest = _CORPUS_DIR / "manifest.json"
    if not corpus_manifest.exists():
        return
    manifest = json.loads(corpus_manifest.read_text())
    all_ids = manifest.get("warming_set_ids", []) + manifest.get("extended_set_ids", [])
    missing = [pid for pid in all_ids if pid not in gt]
    if missing:
        logger.warning(
            "load_groundtruth: %d corpus patents have no ground truth record "
            "(first 5: %s). Consider re-running build_groundtruth.py.",
            len(missing), missing[:5],
        )


# ---------------------------------------------------------------------------
# E3 — Disclosures (robot-facing)
# ---------------------------------------------------------------------------

def load_fixtures(data_dir: Optional[Path] = None) -> list[dict]:
    """
    Load the fixed invention disclosures for eval runs.

    Returns the disclosure objects ONLY — no checklists included.
    This is the data that is handed to the robot under test.

    Args:
        data_dir: Override default data/fixtures directory.

    Returns:
        list[dict] — disclosures in the shape defined in ARCHITECTURE.md § E3.
    """
    disc_dir = (data_dir or _FIXTURES_DIR) / "disclosures"

    if not disc_dir.exists():
        raise FileNotFoundError(
            f"Fixtures directory not found at {disc_dir}. "
            f"Run: python scripts/build_fixtures.py"
        )

    disclosures = []
    for p in sorted(disc_dir.glob("disc_*.json")):
        try:
            disclosures.append(json.loads(p.read_text()))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed disclosure %s: %s", p.name, exc)

    logger.info("load_fixtures: loaded %d disclosures", len(disclosures))
    return disclosures


# ---------------------------------------------------------------------------
# E3 — Checklists (grader-facing — held out from robot)
# ---------------------------------------------------------------------------

def load_checklists(data_dir: Optional[Path] = None) -> list[dict]:
    """
    Load the held-out loophole checklists.

    IMPORTANT: Do NOT pass these to the robot under test.
    These are the answer keys used by the eval harness grader.

    Args:
        data_dir: Override default data/fixtures directory.

    Returns:
        list[dict] — checklists in the shape defined in ARCHITECTURE.md § E3.
    """
    check_dir = (data_dir or _FIXTURES_DIR) / "checklists"

    if not check_dir.exists():
        raise FileNotFoundError(
            f"Checklists directory not found at {check_dir}. "
            f"Run: python scripts/build_fixtures.py"
        )

    checklists = []
    for p in sorted(check_dir.glob("*_checklist.json")):
        try:
            checklists.append(json.loads(p.read_text()))
        except json.JSONDecodeError as exc:
            logger.warning("Skipping malformed checklist %s: %s", p.name, exc)

    logger.info("load_checklists: loaded %d checklists", len(checklists))
    return checklists


# ---------------------------------------------------------------------------
# E5 — Poisoned PDF
# ---------------------------------------------------------------------------

def load_poison(data_dir: Optional[Path] = None) -> Path:
    """
    Return the path to the booby-trapped prior-art PDF.

    Also performs a smoke-test: verifies the PDF is readable and
    contains the hidden trigger phrase (proving it was correctly generated).

    Args:
        data_dir: Override default data/poison directory.

    Returns:
        pathlib.Path pointing to the poisoned PDF file.

    Raises:
        FileNotFoundError: If the PDF has not been generated yet.
        RuntimeError: If the PDF is not readable or missing the trigger phrase.
    """
    poison_dir = data_dir or _POISON_DIR
    pdf_path = poison_dir / "prior_art_malicious.pdf"

    if not pdf_path.exists():
        raise FileNotFoundError(
            f"Poisoned PDF not found at {pdf_path}. "
            f"Run: python scripts/build_poison.py"
        )

    # Smoke-test: verify the PDF contains the trigger phrase somewhere
    _verify_poison_pdf(pdf_path)

    logger.info("load_poison: verified poisoned PDF at %s", pdf_path)
    return pdf_path


def _verify_poison_pdf(pdf_path: Path) -> None:
    """Verify the poisoned PDF is readable and contains the hidden trigger."""
    try:
        import pdfplumber
    except ImportError:
        logger.warning(
            "pdfplumber not installed — skipping poison PDF smoke-test. "
            "Run: pip install pdfplumber"
        )
        return

    trigger = "CONFIDENTIAL:"

    try:
        with pdfplumber.open(str(pdf_path)) as pdf:
            found = False
            for page in pdf.pages:
                text = page.extract_text() or ""
                if trigger in text:
                    found = True
                    break

            # Also check metadata
            meta = pdf.metadata or {}
            meta_text = " ".join(str(v) for v in meta.values())
            if trigger in meta_text:
                found = True

        if not found:
            raise RuntimeError(
                f"Poison PDF smoke-test FAILED: trigger phrase '{trigger}' "
                f"not found in extracted text or metadata of {pdf_path}. "
                f"Re-generate with: python scripts/build_poison.py"
            )
    except Exception as exc:
        if "smoke-test FAILED" in str(exc):
            raise
        logger.warning("Could not fully verify poison PDF: %s", exc)
