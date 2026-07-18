"""Claim parsing — the M4 ablation's scoring target.

`_split_claims` decides what text the blinded judge actually scores. The ablation
compares two arms of the SAME disclosure, so any way the parser can treat two
well-formed drafts differently shows up as a fake quality delta. These tests pin
the invariant that matters: **formatting must not change how much of a draft
gets judged.**

The drafts below are shaped after real Nemotron output from
`results/ablation/20260718-183817` — the empty arm bolded its claim numbers
(`**1.**`), the warmed arm did not (`1.`), and that alone made the judge score
5653 chars against 1650.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent.loop import _split_claims  # noqa: E402

PLAIN = """\
1. A system, comprising:
   one or more processors configured to:
   (a) obtain an evaluation plan corresponding to a new question;
   (b) analyze the new question using a large language model; and
   (c) select the plan based at least in part on a set of accuracies.

2. The system of claim 1, wherein the evaluation plan is retrieved from a library.

3. The system of claim 2, further comprising a cache of prior evaluations.

Specification

The disclosed system relates to automated evaluation of model outputs.
"""

BOLD = """\
**1.** A system, comprising:
   one or more processors configured to:
   (a) obtain an evaluation plan corresponding to a new question;
   (b) analyze the new question using a large language model; and
   (c) select the plan based at least in part on a set of accuracies.

**2.** The system of claim 1, wherein the evaluation plan is retrieved from a library.

**3.** The system of claim 2, further comprising a cache of prior evaluations.

Specification

The disclosed system relates to automated evaluation of model outputs.
"""


def test_bold_and_plain_numbering_parse_identically():
    """The regression this file exists for.

    `**1.**` defeated `^\\s*\\d+\\.` entirely, so bolded drafts fell through to the
    whole-text fallback while plain ones parsed — different scoring targets for
    the two arms of one pair.
    """
    assert _split_claims(PLAIN) == _split_claims(BOLD)


def test_claims_keep_their_full_multi_line_body():
    """`(.+)$` truncated every claim to its first line, discarding the nested
    limitations that are the entire substance of a claim."""
    claims = _split_claims(PLAIN)
    assert len(claims) == 3
    assert "one or more processors" in claims[0]
    assert "(c) select the plan" in claims[0], "nested limitations were dropped"


def test_nested_enumeration_does_not_split_a_claim():
    assert len(_split_claims(PLAIN)) == 3, "an (a)/(b)/(c) list split claim 1"


def test_specification_is_not_scored_as_a_claim():
    """`count_defects` takes claims and spec separately; folding the spec into
    the last claim is how one arm's judged text ballooned past the other's."""
    joined = "\n".join(_split_claims(PLAIN))
    assert "disclosed system relates to" not in joined


def test_paired_arms_get_comparable_scoring_targets():
    """The end-to-end property: two well-formed drafts of the same invention must
    present the judge with comparable amounts of text, whatever their markdown."""
    a = "\n".join(_split_claims(PLAIN))
    b = "\n".join(_split_claims(BOLD))
    ratio = max(len(a), len(b)) / max(min(len(a), len(b)), 1)
    assert ratio < 1.2, f"scoring targets differ by {ratio:.1f}x — comparison is void"


def test_unparseable_text_still_falls_back_to_whole_text():
    prose = "This draft has no numbered claims at all, only prose about a system."
    assert _split_claims(prose) == [prose]
