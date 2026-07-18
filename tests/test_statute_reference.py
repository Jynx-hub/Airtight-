"""MPEP statute reference — coverage, citations, and ablation-safety."""

from agent import loop
from agent.statute_reference import STATUTES, reference_block


def test_covers_the_six_failure_modes_with_citations():
    assert set(STATUTES) == {"101", "102", "103", "112a", "112b", "112f"}
    for text, cite in STATUTES.values():
        assert cite.startswith("MPEP ")  # every standard is cited
        assert "Fix:" in text or "fix:" in text  # each is actionable


def test_reference_block_is_deterministic_and_cited():
    block = reference_block()
    assert block == reference_block()  # stable -> template hash stable
    assert "MPEP 2106" in block and "MPEP 2181" in block  # Alice + means-plus-function present
    assert "Alice/Mayo" in block and "Nautilus" in block  # the controlling standards


def test_reference_is_in_the_drafting_templates():
    ref = reference_block()
    for template in (loop.DRAFT_SYSTEM, loop.CRITIQUE_SYSTEM, loop.REVISE_SYSTEM):
        assert ref in template  # grounds draft, critique, and revise
        assert "{guardrails}" in template  # the memory slot is still there


def test_reference_is_constant_across_ablation_arms():
    # The reference is fixed template text, not the {guardrails} slot — so the
    # scaffold_proof equality (empty vs warmed differ ONLY in the slot) still holds.
    from agent.eval.harness import scaffold_proof

    proof = scaffold_proof([])  # asserts internally; would raise if the reference leaked into the slot
    assert "CRITIQUE_SYSTEM" in proof["templates_sha256"]
