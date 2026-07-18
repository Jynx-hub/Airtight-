"""Statute currency monitor — scope gate, never-fabricates, and ablation safety.

The load-bearing test is `test_monitor_never_touches_the_reference`: the monitor
proposes, a human admits. Nothing here may write into STATUTES, or the ablation's
deterministic template hash could shift mid-run.
"""

import json

import pytest

from agent import statute_monitor as sm


def _relevant_kwargs(**over):
    base = dict(
        title="CAFC holds computer-implemented cache claim §101-eligible",
        holding="A specific improvement to processor cache coherency is eligible; "
                "reciting the abstract idea on a generic computer is not. Fix: claim "
                "the technical improvement.",
        citation="Fed. Cir. (2026)",
        source_url="https://example.invalid/case/1",
        source_type="case",
    )
    base.update(over)
    return base


# --- scope gate + never-fabricates -----------------------------------------

def test_relevant_software_eligibility_candidate_becomes_a_proposal():
    p = sm.to_proposal(**_relevant_kwargs())
    assert p is not None
    assert p.statute == "101"          # bound to the eligibility standard
    assert p.status == "pending"       # nothing is auto-admitted


def test_out_of_domain_candidate_is_dropped():
    # A mechanical/biotech patent case names a basis (§103) but no software signal.
    assert sm.to_proposal(**_relevant_kwargs(
        title="Obviousness of a surgical stapler linkage",
        holding="The claimed mechanical linkage is obvious over the prior art.",
    )) is None


def test_candidate_without_a_source_is_dropped_not_guessed():
    assert sm.to_proposal(**_relevant_kwargs(source_url="")) is None
    assert sm.to_proposal(**_relevant_kwargs(citation="")) is None


def test_candidate_with_no_resolvable_basis_is_dropped():
    # Software signal present, but no statutory basis to bind it to.
    assert sm.to_proposal(**_relevant_kwargs(
        title="USPTO fee schedule update for electronic filing",
        holding="Electronic filing fees for software applications increase in 2026.",
    )) is None


def test_112_subparts_are_distinguished():
    assert sm.to_proposal(**_relevant_kwargs(
        title="§112(f) means-plus-function in a software module claim",
        holding="A 'module for' term in a computer claim invokes §112(f).",
    )).statute == "112f"


# --- queue: dedup + operator decisions --------------------------------------

def test_queue_is_idempotent_and_records_decisions(tmp_path):
    q = tmp_path / "proposals.jsonl"
    p = sm.to_proposal(**_relevant_kwargs())
    assert sm.add_proposals([p], q) == 1
    assert sm.add_proposals([p], q) == 0          # same id -> no duplicate
    assert sm.set_status(p.id, "approved", q) is True
    assert sm.load_proposals(q)[0].status == "approved"
    assert sm.set_status("nope", "approved", q) is False


def test_approve_does_not_overwrite_on_refetch(tmp_path):
    q = tmp_path / "proposals.jsonl"
    p = sm.to_proposal(**_relevant_kwargs())
    sm.add_proposals([p], q)
    sm.set_status(p.id, "rejected", q)
    sm.add_proposals([p], q)                       # a later fetch sees it again
    assert sm.load_proposals(q)[0].status == "rejected"   # decision survives


# --- ablation safety: the monitor must never mutate the reference -----------

def test_monitor_never_touches_the_reference():
    import agent.statute_reference as ref
    before = ref.reference_block()
    # Everything the module does client-side, exercised:
    p = sm.to_proposal(**_relevant_kwargs())
    sm.render_admission(p)
    assert ref.reference_block() == before        # byte-identical -> template hash stable
    # And it doesn't reach into the curated dict at all.
    src = (sm.PROPOSALS.parent / "statute_monitor.py").read_text()
    assert "from agent.statute_reference import" not in src
    assert "STATUTES[" not in src and "STATUTES.update" not in src


def test_admission_card_renders_a_pasteable_entry():
    p = sm.to_proposal(**_relevant_kwargs())
    card = sm.render_admission(p)
    assert p.source_url in card
    assert '"101": (' in card                     # the exact STATUTES key line to paste


def test_admission_snippet_is_valid_python_even_with_quotes():
    # A real §101 holding routinely contains double quotes ('the "abstract idea"
    # doctrine'); the pasted STATUTES entry must still parse.
    import ast
    import textwrap

    p = sm.to_proposal(**_relevant_kwargs(
        holding='The "abstract idea" of §101 must be an "inventive concept"; software fix: '
                'recite a specific technical improvement.',
        citation='In re "Quoted" Corp., Fed. Cir. (2026)',
    ))
    # Pull the "key": (...) tuple out of the card and parse it inside a dict literal.
    snippet = "{\n" + sm.render_admission(p).split("── verify")[1].split("\n", 1)[1] + "\n}"
    tree = ast.parse(textwrap.dedent(snippet), mode="eval")  # raises SyntaxError if unescaped
    assert isinstance(tree.body, ast.Dict)


# --- offline rehearsal (no network/keys), mirrors ingest --fake-clean -------

def test_fake_source_is_relevant_and_admissible():
    cands = [sm.to_proposal(**raw) for raw in sm.FAKE_SOURCE]
    assert all(c is not None for c in cands)
    assert cands[0].statute == "101"


def test_keyless_sources_skip_cleanly_without_creds(monkeypatch):
    monkeypatch.delenv("COURTLISTENER_API_TOKEN", raising=False)
    monkeypatch.delenv("CONGRESS_API_KEY", raising=False)
    assert sm.fetch_courtlistener() == []          # no key, no pull — no network hit
    assert sm.fetch_congress() == []
