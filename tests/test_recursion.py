"""Block B — recursion: the revise turn (B1) and bounded distillation (B3)."""

from airtight import Disclosure
from agent import loop


class _Reply:
    def __init__(self, text):
        self.text = text


def _disc():
    return Disclosure(id="d1", title="t", inventors=["a"], technology_class="G06F",
                      summary="s", details="d")


def test_revise_turn_feeds_critique_back_and_converges(monkeypatch):
    """B1: the examiner's defect is fed back, the draft is revised, and the re-critique
    comes back clean → the loop converges and keeps the REVISED text."""
    state = {"critiques": 0, "revised": False}

    def fake(messages, role="draft", **kw):
        sys = messages[0]["content"]
        if "planning module" in sys:
            return _Reply("{}")
        if "revising your own draft" in sys:
            state["revised"] = True
            return _Reply("1. A widget comprising a thing; wherein the thing is coupled.")
        if "hostile patent examiner" in sys:
            state["critiques"] += 1
            if state["critiques"] == 1:
                return _Reply("- antecedent-basis: 'said thing' has no prior 'a thing'")
            return _Reply("")  # clean after the revision
        return _Reply("1. A widget comprising said thing.")  # defective first draft

    monkeypatch.setattr(loop, "call_model", fake)
    d = loop.draft_patent(_disc())

    assert state["revised"] is True            # a revise turn actually ran
    assert state["critiques"] == 2             # critiqued → revised → re-critiqued
    assert "a thing" in d.specification        # specification is the REVISED draft, not the defective one
    assert "said thing" not in d.specification
    assert d.critique_notes == []              # converged: nothing left for the examiner


def test_revise_stops_at_max_rounds(monkeypatch):
    """B1: if the examiner keeps finding NEW defects, the loop stops at revise_rounds
    instead of looping forever, and the surviving defects are reported."""
    state = {"critiques": 0, "revisions": 0}

    def fake(messages, role="draft", **kw):
        sys = messages[0]["content"]
        if "planning module" in sys:
            return _Reply("{}")
        if "revising your own draft" in sys:
            state["revisions"] += 1
            return _Reply(f"draft revision {state['revisions']}")
        if "hostile patent examiner" in sys:
            state["critiques"] += 1
            return _Reply(f"- a brand new defect #{state['critiques']}")  # never converges
        return _Reply("draft v0")

    monkeypatch.setattr(loop, "call_model", fake)
    d = loop.draft_patent(_disc(), revise_rounds=2)

    assert state["revisions"] == 2             # exactly the cap
    assert state["critiques"] == 3             # initial + 2 re-critiques
    assert d.critique_notes                    # defects still stand (didn't converge)


# --- B3: bounded distillation ---

def test_b3_defect_lines_keeps_bullets_drops_chrome():
    from agent.episodes import defect_lines
    notes = [
        "Here are the defects:",                          # preamble — drop
        "## Severe",                                      # header — drop
        "- antecedent-basis gap in claim 1 wording",      # keep
        "* means-plus-function overbreadth in claim 3",   # keep
        "- ok",                                           # too short — drop
        "1. §112 indefiniteness on 'substantially'",      # numbered defect — keep
    ]
    assert defect_lines(notes) == [
        "antecedent-basis gap in claim 1 wording",
        "means-plus-function overbreadth in claim 3",
        "§112 indefiniteness on 'substantially'",
    ]


def test_b3_caps_the_count():
    from agent.episodes import defect_lines
    notes = [f"- defect number {i} with enough real text here" for i in range(20)]
    assert len(defect_lines(notes, cap=8)) == 8


# --- B2: episodic memory actually compounds ---

def test_b2_episode_compounds_into_next_retrieval(tmp_path):
    from airtight import Draft
    from agent.episodes import CompositeStore, EpisodeStore, compress_run
    from agent.memory import LoopholeStore

    disc = _disc()
    store = EpisodeStore([], directory=tmp_path)
    draft = Draft(disclosure_id=disc.id, claims=["c"], specification="s",
                  critique_notes=["- means-plus-function overbreadth in the coupling claim"],
                  loopholes_closed=[])
    store.record(compress_run(disc, [], draft, mode="live"))

    reloaded = EpisodeStore.load(tmp_path)  # persisted to disk and read back
    assert len(reloaded) == 1

    # next run: an empty warming corpus + the accumulated episode surfaces the lesson
    composite = CompositeStore(LoopholeStore([]), reloaded)
    got = composite.retrieve(disc, k=5)
    assert any("means-plus-function" in r.pattern for r in got)


def test_b2_missing_episode_dir_is_empty_not_an_error(tmp_path):
    from agent.episodes import EpisodeStore
    assert len(EpisodeStore.load(tmp_path / "does-not-exist")) == 0
