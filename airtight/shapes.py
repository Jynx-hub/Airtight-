"""Cross-lane data contract: the shapes all four lanes speak.

Change these only with the whole team's sign-off (WORKSTREAMS.md shared setup,
step 3). Person 1's loaders produce them, the agent consumes and returns them,
Person 3's surface renders their JSON.
"""

import re

from pydantic import BaseModel, Field, model_validator

# §101 eligibility · §102 anticipation · §103 obviousness · §112 definiteness/enablement
_STATUTE_RE = re.compile(r"[§\s(]\s*(101|102|103|112)\b")


def statute_of(*texts: str) -> str:
    """Pull the statutory basis (101/102/103/112) out of free text, '' if none.
    The producers encode it in the pattern string ('§103 — obviousness …')."""
    for text in texts:
        m = _STATUTE_RE.search(f" {text}")
        if m:
            return m.group(1)
    return ""


class Disclosure(BaseModel):
    """An invention disclosure — the input to every drafting run."""

    id: str
    title: str
    inventors: list[str]
    technology_class: str  # CPC class, e.g. "G06F"
    summary: str
    details: str


class LoopholeRecord(BaseModel):
    """One edge case mined from ground truth (PTAB decision / office action)."""

    id: str
    pattern: str  # e.g. "antecedent-basis gap", "means-plus-function overbreadth"
    claim_shape: str  # the claim language that triggered it
    technology_class: str
    remedy: str
    source: str  # citation to the PTAB decision / office action
    statute: str = ""  # 101 | 102 | 103 | 112 | "" — the failure mode retrieval balances on

    @model_validator(mode="after")
    def _derive_statute(self):
        # Back-compat: existing records carry the statute in the pattern text
        # ("§103 — …"), so derive it when a producer didn't set it explicitly.
        if not self.statute:
            self.statute = statute_of(self.pattern, self.source)
        return self


class Draft(BaseModel):
    """A drafted patent, plus what the agent caught on the way."""

    disclosure_id: str
    claims: list[str]
    specification: str
    critique_notes: list[str] = Field(default_factory=list)
    loopholes_closed: list[str] = Field(default_factory=list)  # LoopholeRecord ids


class EvalResult(BaseModel):
    """One condition of the M4 ablation, ready for Person 3's chart."""

    disclosure_id: str
    condition: str  # "empty" | "warmed"
    loopholes_caught: int
    checklist_size: int
    drafting_seconds: float
    defect_count: int
