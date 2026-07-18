"""
src/extractors/oa_extractor.py
===============================
Rule-based text parser for USPTO Office Action documents.

Given the raw text of an Office Action, this module:
  1. Detects statutory rejection blocks (§112, §102, §103)
  2. Isolates the triggering claim phrase
  3. Extracts the examiner's rationale (sentence window)
  4. Detects whether a subsequent amendment resolved the rejection

Output schema per rejection::

    {
        "vulnerable_claim_shape":   str,
        "statutory_defect_category": str,   # "§112" | "§102" | "§103"
        "examiner_rationale":       str,
        "remediated_claim_shape":   str | None,
    }

Design notes:
  - Pure Python + regex — no ML dependencies.
  - Designed for best-effort extraction on OCR-noisy text.
  - extraction_confidence reflects match quality (1.0 = strong, <1.0 = heuristic).
"""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Optional

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(__file__))))
import config


# ---------------------------------------------------------------------------
# Compiled pattern sets
# ---------------------------------------------------------------------------

# Maps defect category -> list of compiled patterns
_REJECTION_PATTERNS: dict[str, list[re.Pattern]] = {
    cat: [re.compile(p, re.IGNORECASE | re.UNICODE) for p in patterns]
    for cat, patterns in config.REJECTION_MARKERS.items()
}

_CLAIM_PHRASE_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in config.CLAIM_PHRASE_PATTERNS
]

_AMENDMENT_PATTERNS: list[re.Pattern] = [
    re.compile(p, re.IGNORECASE | re.UNICODE)
    for p in config.AMENDMENT_MARKERS
]

# Split text into sentences (rough — handles "U.S.C." abbreviations)
_SENTENCE_SPLIT = re.compile(r"(?<!\w\.\w.)(?<![A-Z][a-z]\.)(?<=\.|\?)\s")

# Generic claim number reference
_CLAIM_NUM_RE = re.compile(r"\b[Cc]laim[s]?\s+(\d+(?:[,\s]+and\s+\d+)*)", re.IGNORECASE)


# ---------------------------------------------------------------------------
# Data structures
# ---------------------------------------------------------------------------

@dataclass
class ExtractedDefect:
    """A single statutory rejection extracted from an Office Action."""

    vulnerable_claim_shape: str
    statutory_defect_category: str   # §112 | §102 | §103
    examiner_rationale: str
    remediated_claim_shape: Optional[str]
    extraction_confidence: float = 1.0

    def to_dict(self) -> dict:
        return {
            "vulnerable_claim_shape":    self.vulnerable_claim_shape,
            "statutory_defect_category": self.statutory_defect_category,
            "examiner_rationale":        self.examiner_rationale,
            "remediated_claim_shape":    self.remediated_claim_shape or "",
        }

    def fingerprint(self, app_number: str) -> str:
        """Deterministic ID for deduplication."""
        raw = f"{app_number}|{self.statutory_defect_category}|{self.vulnerable_claim_shape[:100]}"
        return hashlib.sha1(raw.encode()).hexdigest()


# ---------------------------------------------------------------------------
# Core extraction logic
# ---------------------------------------------------------------------------

class OAExtractor:
    """
    Stateless extractor — call extract() for each document.
    """

    def extract(
        self,
        oa_text: str,
        amendment_text: str = "",
    ) -> list[ExtractedDefect]:
        """
        Extract all statutory rejection records from Office Action text.

        Args:
            oa_text: Raw text of the Office Action document.
            amendment_text: Optional text of the applicant's response/amendment
                            (used to populate remediated_claim_shape).

        Returns:
            List of ExtractedDefect instances (may be empty if no rejections found).
        """
        if not oa_text or len(oa_text) < 50:
            return []

        results: list[ExtractedDefect] = []

        # Split into segments around each detected rejection
        for category, patterns in _REJECTION_PATTERNS.items():
            for pattern in patterns:
                for match in pattern.finditer(oa_text):
                    start = max(0, match.start() - 100)
                    end = min(len(oa_text), match.end() + config.RATIONALE_WINDOW)
                    segment = oa_text[start:end]

                    rationale = self._extract_rationale(segment, match.group())
                    claim_shape = self._extract_claim_shape(segment, oa_text, start)
                    remediation = self._extract_remediation(amendment_text, category) if amendment_text else None
                    confidence = self._score_confidence(claim_shape, rationale, amendment_text)

                    # Skip if we couldn't find any meaningful content
                    if not claim_shape and not rationale:
                        continue

                    defect = ExtractedDefect(
                        vulnerable_claim_shape=claim_shape or f"[claim near offset {match.start()}]",
                        statutory_defect_category=category,
                        examiner_rationale=rationale or segment[:300].strip(),
                        remediated_claim_shape=remediation,
                        extraction_confidence=confidence,
                    )
                    results.append(defect)

        # Deduplicate: same category + same leading claim text
        seen: set[tuple[str, str]] = set()
        deduped: list[ExtractedDefect] = []
        for d in results:
            key = (d.statutory_defect_category, d.vulnerable_claim_shape[:80])
            if key not in seen:
                seen.add(key)
                deduped.append(d)

        return deduped

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _extract_rationale(self, segment: str, trigger: str) -> str:
        """
        Extract the examiner's rationale sentences near the rejection trigger.

        Strategy:
          1. Find the sentence containing the trigger.
          2. Return that sentence plus the following 2 sentences.
        """
        sentences = _SENTENCE_SPLIT.split(segment)
        for i, sent in enumerate(sentences):
            if trigger.lower()[:15] in sent.lower():
                window = sentences[i : i + 3]
                rationale = " ".join(s.strip() for s in window if s.strip())
                return _clean_text(rationale)[:800]
        # Fallback: return the first 400 chars of the segment
        return _clean_text(segment[:400])

    def _extract_claim_shape(
        self, segment: str, full_text: str, segment_offset: int
    ) -> str:
        """
        Find the exact claim phrase or structural element that triggered the rejection.

        Tries, in order:
          1. Quoted phrase patterns (most reliable)
          2. Claim number reference → look up that claim's text in the full document
          3. Heuristic: first quoted string in the segment
        """
        # 1. Named patterns
        for pat in _CLAIM_PHRASE_PATTERNS:
            m = pat.search(segment)
            if m:
                return _clean_text(m.group(1))

        # 2. Claim number → look up claim text
        m = _CLAIM_NUM_RE.search(segment)
        if m:
            claim_num = m.group(1).strip().split()[0]  # take first number
            claim_text = self._find_claim_in_doc(full_text, claim_num)
            if claim_text:
                return _clean_text(claim_text[:300])

        # 3. Fallback: first quoted string ≥10 chars
        quoted = re.findall(r'"([^"]{10,200})"', segment)
        if quoted:
            return _clean_text(quoted[0])

        return ""

    def _find_claim_in_doc(self, text: str, claim_num: str) -> str:
        """
        Locate the independent claim text for a given claim number.

        Looks for patterns like:
          "Claim 1. A method comprising..."
          "1. A system for..."
        """
        patterns = [
            rf"\bClaim\s+{re.escape(claim_num)}\.\s+(.{{20,500}}?)(?=\bClaim\s+\d+\b|\Z)",
            rf"^\s*{re.escape(claim_num)}\.\s+(.{{20,500}}?)(?=^\s*\d+\.\s+|\Z)",
        ]
        for pat in patterns:
            m = re.search(pat, text, re.IGNORECASE | re.DOTALL | re.MULTILINE)
            if m:
                return m.group(1).strip()
        return ""

    def _extract_remediation(self, amendment_text: str, category: str) -> Optional[str]:
        """
        Find claim language in the applicant's amendment that addresses
        the given defect category.

        Returns the amended claim text if found, else None.
        """
        if not amendment_text:
            return None

        # Check the amendment text actually references an amendment
        has_amendment = any(p.search(amendment_text) for p in _AMENDMENT_PATTERNS)
        if not has_amendment:
            return None

        # Try to find amended claim text (lines starting with claim numbers
        # after an "Amended" header)
        amended_block = re.search(
            r"(?:[Aa]mended?|[Cc]ancelled?\s+and\s+replaced?)[^\n]*\n"
            r"((?:.|\n){20,600}?)(?=\n\s*(?:\d+\.|Claim\s+\d+|\Z))",
            amendment_text,
        )
        if amended_block:
            return _clean_text(amended_block.group(1)[:400])

        # Fallback: first quoted phrase in the amendment
        quoted = re.findall(r'"([^"]{10,250})"', amendment_text)
        if quoted:
            return _clean_text(quoted[0])

        return None

    @staticmethod
    def _score_confidence(
        claim_shape: str, rationale: str, amendment_text: str
    ) -> float:
        """
        Assign an extraction confidence score [0.0, 1.0].

        Rules:
          - 0.3 base
          - +0.3 if claim_shape found via named pattern (not heuristic)
          - +0.2 if rationale is ≥50 chars
          - +0.2 if amendment resolved the rejection
        """
        score = 0.3
        if claim_shape and not claim_shape.startswith("[claim near"):
            score += 0.3
        if len(rationale) >= 50:
            score += 0.2
        if amendment_text and any(
            p.search(amendment_text) for p in _AMENDMENT_PATTERNS
        ):
            score += 0.2
        return round(min(score, 1.0), 2)


# ---------------------------------------------------------------------------
# Utilities
# ---------------------------------------------------------------------------

def _clean_text(text: str) -> str:
    """Normalize whitespace and remove common OCR noise."""
    text = re.sub(r"\s+", " ", text)
    text = re.sub(r"[^\x20-\x7E\n]", " ", text)   # strip non-ASCII
    text = re.sub(r"[ \t]{2,}", " ", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

_default_extractor = OAExtractor()


def extract_defects(
    oa_text: str,
    amendment_text: str = "",
) -> list[dict]:
    """
    Convenience wrapper. Returns a list of raw dicts matching the output schema::

        {
            "vulnerable_claim_shape":    str,
            "statutory_defect_category": str,
            "examiner_rationale":        str,
            "remediated_claim_shape":    str,
        }
    """
    defects = _default_extractor.extract(oa_text, amendment_text)
    return [d.to_dict() for d in defects]
