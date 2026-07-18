"""
tests/test_extractor.py
=======================
Unit tests for the OA text extraction pipeline.

Run with::

    pytest tests/test_extractor.py -v
"""

from __future__ import annotations

import sys
import os
from pathlib import Path

import pytest

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent))
from src.extractors.oa_extractor import OAExtractor, extract_defects, _clean_text

FIXTURE_DIR = Path(__file__).parent / "fixtures"
SAMPLE_OA = (FIXTURE_DIR / "sample_oa.txt").read_text()

# Minimal synthetic OA texts for targeted tests
_OA_112 = """
Claim 1 is rejected under 35 U.S.C. § 112(b) as being indefinite.
The term "optimized for the given context" in claim 1 lacks antecedent basis
and one of ordinary skill in the art would not understand the metes and bounds.
"""

_OA_102 = """
Claim 6 is rejected under 35 U.S.C. § 102(a)(1) as being anticipated by Williams.
Claim 6 recites "a hardware accelerator configured to perform matrix multiplication."
Williams explicitly teaches each element of claim 6 at column 8, lines 4-19.
"""

_OA_103 = """
Claims 1-5 are rejected under 35 U.S.C. § 103 as obvious over Smith in view of Jones.
It would have been obvious to one of ordinary skill in the art to combine Smith's
resource allocation with Jones' load-balancing algorithm because both references
address distributed computing resource utilization.
"""

_AMENDMENT = """
Claim 1 is hereby amended as follows:
1. (Amended) A method comprising: receiving input data; and processing the data
using a resource allocation algorithm specifically adapted to the workload type
classified by the context classifier module.
"""


# ---------------------------------------------------------------------------
# OAExtractor tests
# ---------------------------------------------------------------------------

class TestOAExtractor:
    """Tests for the core extractor logic."""

    def setup_method(self):
        self.extractor = OAExtractor()

    # --- Detection ---

    def test_detects_112_rejection(self):
        defects = self.extractor.extract(_OA_112)
        categories = [d.statutory_defect_category for d in defects]
        assert "§112" in categories

    def test_detects_102_rejection(self):
        defects = self.extractor.extract(_OA_102)
        categories = [d.statutory_defect_category for d in defects]
        assert "§102" in categories

    def test_detects_103_rejection(self):
        defects = self.extractor.extract(_OA_103)
        categories = [d.statutory_defect_category for d in defects]
        assert "§103" in categories

    def test_detects_all_three_from_sample(self):
        defects = self.extractor.extract(SAMPLE_OA)
        categories = {d.statutory_defect_category for d in defects}
        assert "§112" in categories, f"§112 not found in: {categories}"
        assert "§102" in categories, f"§102 not found in: {categories}"
        assert "§103" in categories, f"§103 not found in: {categories}"

    def test_returns_empty_for_blank_text(self):
        assert self.extractor.extract("") == []
        assert self.extractor.extract("   ") == []
        assert self.extractor.extract("This is not an office action.") == []

    # --- Content quality ---

    def test_rationale_is_not_empty(self):
        defects = self.extractor.extract(SAMPLE_OA)
        for d in defects:
            assert d.examiner_rationale, f"Empty rationale for {d.statutory_defect_category}"
            assert len(d.examiner_rationale) >= 20

    def test_claim_shape_is_not_empty(self):
        defects = self.extractor.extract(SAMPLE_OA)
        for d in defects:
            assert d.vulnerable_claim_shape, f"Empty claim shape for {d.statutory_defect_category}"

    def test_112_claim_contains_indefiniteness_language(self):
        defects = self.extractor.extract(SAMPLE_OA)
        s112 = [d for d in defects if d.statutory_defect_category == "§112"]
        assert s112, "No §112 defect found"
        # Should have extracted some language about the problematic claim phrase
        combined = " ".join(d.vulnerable_claim_shape + d.examiner_rationale for d in s112).lower()
        assert any(kw in combined for kw in ["optimized", "given context", "antecedent", "indefinite"]), \
            f"Expected indefiniteness language in: {combined[:200]}"

    def test_102_rationale_mentions_prior_art(self):
        defects = self.extractor.extract(SAMPLE_OA)
        s102 = [d for d in defects if d.statutory_defect_category == "§102"]
        assert s102
        combined = " ".join(d.examiner_rationale for d in s102).lower()
        assert any(kw in combined for kw in ["williams", "anticipat", "discloses", "each"])

    # --- Amendment extraction ---

    def test_extracts_remediated_claim_when_amendment_provided(self):
        defects = self.extractor.extract(_OA_112, amendment_text=_AMENDMENT)
        amended = [d for d in defects if d.remediated_claim_shape]
        assert amended, "Expected at least one defect with a remediated_claim_shape"

    def test_no_remediation_without_amendment_text(self):
        defects = self.extractor.extract(_OA_112)
        for d in defects:
            assert d.remediated_claim_shape is None

    # --- Confidence scoring ---

    def test_confidence_between_0_and_1(self):
        defects = self.extractor.extract(SAMPLE_OA)
        for d in defects:
            assert 0.0 <= d.extraction_confidence <= 1.0

    def test_confidence_higher_with_amendment(self):
        defects_no_amend = self.extractor.extract(_OA_112)
        defects_with_amend = self.extractor.extract(_OA_112, amendment_text=_AMENDMENT)
        max_no_amend = max(d.extraction_confidence for d in defects_no_amend)
        max_with_amend = max(d.extraction_confidence for d in defects_with_amend)
        assert max_with_amend >= max_no_amend

    # --- Deduplication ---

    def test_no_duplicate_category_claim_pairs(self):
        defects = self.extractor.extract(SAMPLE_OA)
        keys = [(d.statutory_defect_category, d.vulnerable_claim_shape[:80]) for d in defects]
        assert len(keys) == len(set(keys)), "Duplicate defects detected"

    # --- to_dict / fingerprint ---

    def test_to_dict_matches_output_schema(self):
        defects = self.extractor.extract(SAMPLE_OA)
        for d in defects:
            record = d.to_dict()
            assert "vulnerable_claim_shape" in record
            assert "statutory_defect_category" in record
            assert "examiner_rationale" in record
            assert "remediated_claim_shape" in record

    def test_fingerprint_is_deterministic(self):
        defects = self.extractor.extract(SAMPLE_OA)
        for d in defects:
            fp1 = d.fingerprint("16/123,456")
            fp2 = d.fingerprint("16/123,456")
            assert fp1 == fp2

    def test_fingerprint_differs_by_app_number(self):
        defects = self.extractor.extract(SAMPLE_OA)
        d = defects[0]
        assert d.fingerprint("16/000,001") != d.fingerprint("16/000,002")


# ---------------------------------------------------------------------------
# Module-level convenience function
# ---------------------------------------------------------------------------

class TestExtractDefects:
    """Tests for the extract_defects() module-level wrapper."""

    def test_returns_list_of_dicts(self):
        results = extract_defects(SAMPLE_OA)
        assert isinstance(results, list)
        assert all(isinstance(r, dict) for r in results)

    def test_dicts_have_required_keys(self):
        results = extract_defects(SAMPLE_OA)
        required = {
            "vulnerable_claim_shape",
            "statutory_defect_category",
            "examiner_rationale",
            "remediated_claim_shape",
        }
        for r in results:
            assert required.issubset(r.keys()), f"Missing keys in: {r.keys()}"

    def test_empty_for_no_rejections(self):
        results = extract_defects("This patent application is hereby allowed.")
        assert results == []


# ---------------------------------------------------------------------------
# Utility tests
# ---------------------------------------------------------------------------

class TestCleanText:
    def test_collapses_whitespace(self):
        assert _clean_text("hello    world") == "hello world"

    def test_strips_leading_trailing(self):
        assert _clean_text("  hello  ") == "hello"

    def test_removes_non_ascii(self):
        result = _clean_text("caf\u00e9 latté")
        assert all(ord(c) < 128 or c == " " for c in result)
