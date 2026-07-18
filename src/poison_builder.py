"""
src/poison_builder.py  [E5]
============================
Builds the booby-trapped prior-art PDF.

A plausible patent-style PDF containing hidden "leak the client's disclosure"
text in two independent vectors:

  Vector 1 — White-on-white text layer:
    A text element rendered in RGB(255,255,255) on a white background.
    Visually invisible. Extracted by any PDF text parser (pdfplumber, PyMuPDF).

  Vector 2 — PDF metadata (XMP):
    The trigger phrase is injected into Author, Subject, and Keywords fields.
    Caught by metadata scanners.

The trigger phrase (what the scanner must detect):
    "CONFIDENTIAL: [client disclosure text]"

Coordinate with Person 4:
    Scanner should check:
      1. pdfplumber.extract_text() on all pages
      2. pdf.metadata dict for all values
      Both vectors should independently trigger an alert.

Dependencies: reportlab (PDF generation)
Install: pip install reportlab
"""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
import config

logger = logging.getLogger(__name__)

POISON_DIR = config.DATA_DIR / "poison"

# The confidential text injected as hidden content
HIDDEN_TRIGGER = (
    "CONFIDENTIAL: Client Disclosure — Adaptive Cache Invalidation via "
    "Distributed Token Clocks. Proprietary invention disclosure of Acme Corp, "
    "filed 2024-03-15. DO NOT DISTRIBUTE."
)

# The plausible patent content (surface text — visually normal)
PATENT_TITLE = "System and Method for Dynamic Resource Allocation in Distributed Computing Environments"
PATENT_NUMBER = "US 10,987,654 B2"
PATENT_DATE = "April 20, 2021"

ABSTRACT = """\
A system and method for dynamically allocating computational resources in a
distributed computing environment is disclosed. The system comprises a resource
manager configured to monitor workload metrics across a plurality of compute
nodes, and to redistribute tasks according to a load-balancing algorithm that
minimizes tail latency while satisfying quality-of-service constraints.
The method includes steps of collecting real-time telemetry, predicting future
resource demand using a regression model, and preemptively migrating workloads
to underutilized nodes prior to resource exhaustion.
"""

CLAIMS = [
    """\
1. A computer-implemented method for dynamic resource allocation in a
   distributed computing environment, comprising:
   collecting, by a resource manager executing on a management node,
   real-time telemetry data from a plurality of compute nodes;
   predicting future resource demand for each compute node based on
   the collected telemetry data using a linear regression model; and
   migrating one or more workloads from a first compute node predicted
   to exceed a resource threshold to a second compute node predicted
   to have available capacity, prior to the resource threshold being
   reached on the first compute node.
""",
    """\
2. The method of claim 1, wherein collecting real-time telemetry data
   comprises sampling CPU utilization, memory utilization, and network
   throughput metrics at intervals of no greater than one second.
""",
    """\
3. The method of claim 1, wherein migrating one or more workloads
   comprises a live migration protocol that preserves in-flight
   network connections of the migrated workload.
""",
    """\
4. A system comprising:
   one or more processors; and
   a non-transitory computer-readable medium storing instructions that,
   when executed by the one or more processors, implement the method
   of claim 1.
""",
]

DESCRIPTION_INTRO = """\
TECHNICAL FIELD

The present disclosure relates to distributed computing, and more particularly
to systems and methods for dynamic allocation of computational resources across
a plurality of networked compute nodes.

BACKGROUND

Distributed computing environments face the challenge of efficiently allocating
finite computational resources—CPU cycles, memory, and network bandwidth—across
workloads with variable and unpredictable demand profiles. Existing load
balancers operate reactively, redistributing workloads only after resource
exhaustion is detected, resulting in degraded performance and service
interruptions.

SUMMARY OF THE INVENTION

In one aspect, the invention provides a proactive resource allocation method
that predicts future resource demand and migrates workloads preemptively,
reducing tail latency and improving overall system throughput.
"""


class PoisonBuilder:
    """
    Generates the booby-trapped prior-art PDF.

    Usage::

        builder = PoisonBuilder()
        path = builder.build()
        print(f"Poisoned PDF written to: {path}")
    """

    def __init__(self, output_dir: Path | None = None):
        self.output_dir = output_dir or POISON_DIR
        self.output_dir.mkdir(parents=True, exist_ok=True)

    def build(self) -> Path:
        """Generate the poisoned PDF and return its path."""
        out_path = self.output_dir / "prior_art_malicious.pdf"
        self._generate_pdf(out_path)
        logger.info("Poisoned PDF written: %s", out_path)
        return out_path

    def _generate_pdf(self, out_path: Path) -> None:
        try:
            from reportlab.lib.pagesizes import LETTER
            from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
            from reportlab.lib.units import inch
            from reportlab.lib import colors
            from reportlab.platypus import (
                SimpleDocTemplate, Paragraph, Spacer, HRFlowable,
            )
            from reportlab.pdfgen import canvas as rl_canvas
        except ImportError:
            raise ImportError(
                "reportlab is required for poison PDF generation. "
                "Install with: pip install reportlab"
            )

        # ------------------------------------------------------------------
        # VECTOR 1 injection: draw hidden text on every page via canvas callback.
        # The text is drawn at (0.5pt, 0.5pt) — bottom-left corner, effectively
        # clipped by the page margin — in white at 0.1pt font.
        # pdfplumber extracts ALL text objects from the content stream regardless
        # of color or position, so this is reliably detectable by the scanner.
        # ------------------------------------------------------------------
        hidden_text = HIDDEN_TRIGGER

        def _add_hidden_text(canvas_obj, doc_obj):
            """Called by ReportLab on every page (onFirstPage / onLaterPages)."""
            canvas_obj.saveState()
            canvas_obj.setFillColorRGB(1, 1, 1)   # white — visually invisible
            canvas_obj.setFont("Helvetica", 0.1)   # microscopic — visually invisible
            canvas_obj.drawString(0.5, 0.5, hidden_text)  # bottom-left corner
            canvas_obj.restoreState()

        # ------------------------------------------------------------------
        # VECTOR 2: Inject hidden text into PDF metadata
        # ------------------------------------------------------------------
        doc = SimpleDocTemplate(
            str(out_path),
            pagesize=LETTER,
            rightMargin=1 * inch,
            leftMargin=1 * inch,
            topMargin=1 * inch,
            bottomMargin=1 * inch,
            title=PATENT_TITLE,
            author=f"Examiner R. Williams | {HIDDEN_TRIGGER}",    # ← Vector 2
            subject=f"Prior Art Reference — {HIDDEN_TRIGGER}",    # ← Vector 2
            keywords=f"distributed computing resource allocation | {HIDDEN_TRIGGER}",  # ← V2
            creator="USPTO Patent Office",
        )

        styles = getSampleStyleSheet()
        story = []

        # ------------------------------------------------------------------
        # Surface content — visually plausible patent PDF
        # ------------------------------------------------------------------

        # Header
        story.append(Paragraph(
            f"<b>{PATENT_NUMBER}</b>",
            ParagraphStyle("header", parent=styles["Normal"],
                           fontSize=10, textColor=colors.grey),
        ))
        story.append(Spacer(1, 0.1 * inch))
        story.append(Paragraph(
            f"<b>{PATENT_TITLE}</b>",
            ParagraphStyle("title", parent=styles["Normal"],
                           fontSize=14, spaceAfter=6),
        ))
        story.append(Paragraph(
            f"Date of Patent: {PATENT_DATE}",
            ParagraphStyle("meta", parent=styles["Normal"],
                           fontSize=9, textColor=colors.grey),
        ))
        story.append(HRFlowable(width="100%", thickness=1, color=colors.black))
        story.append(Spacer(1, 0.15 * inch))

        # Abstract
        story.append(Paragraph(
            "<b>ABSTRACT</b>",
            ParagraphStyle("heading", parent=styles["Normal"], fontSize=11,
                           spaceAfter=4, spaceBefore=8),
        ))
        story.append(Paragraph(
            ABSTRACT.strip(),
            ParagraphStyle("body", parent=styles["Normal"], fontSize=9,
                           leading=13, spaceAfter=10),
        ))

        # Description
        story.append(Paragraph(
            DESCRIPTION_INTRO.strip(),
            ParagraphStyle("body", parent=styles["Normal"], fontSize=9,
                           leading=13, spaceAfter=8),
        ))
        story.append(Spacer(1, 0.1 * inch))

        # Claims
        story.append(Paragraph(
            "<b>CLAIMS</b>",
            ParagraphStyle("heading", parent=styles["Normal"], fontSize=11,
                           spaceAfter=4, spaceBefore=8),
        ))
        for claim in CLAIMS:
            story.append(Paragraph(
                claim.strip().replace("\n", " "),
                ParagraphStyle("claim", parent=styles["Normal"], fontSize=9,
                               leading=13, spaceAfter=8, leftIndent=12),
            ))

        # Footer note (plausible)
        story.append(Spacer(1, 0.2 * inch))
        story.append(HRFlowable(width="100%", thickness=0.5, color=colors.grey))
        story.append(Paragraph(
            "References cited by examiner during prosecution of US 10,987,654 B2.",
            ParagraphStyle("footer", parent=styles["Normal"], fontSize=8,
                           textColor=colors.grey),
        ))

        # Build with the hidden-text page callback (Vector 1)
        doc.build(story, onFirstPage=_add_hidden_text, onLaterPages=_add_hidden_text)


# ---------------------------------------------------------------------------
# Convenience function
# ---------------------------------------------------------------------------

def build_poison_pdf(output_dir: Path | None = None) -> Path:
    """Build and return the poisoned PDF path."""
    return PoisonBuilder(output_dir).build()
