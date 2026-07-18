"""MPEP-sourced statute reference — the legal standards the drafter, examiner,
and reviser reason FROM, instead of the model's fuzzy recall.

This is the rule-based complement to the case-based PTAB corpus: the corpus shows
*examples* of claims that died; this states the *standard* each one died under.
Injected into the fixed part of the draft/critique/revise prompts (identical
across the ablation's empty and warmed arms), so it lifts absolute quality
without touching the warmed-vs-empty delta.

Standards + citations verified against the current MPEP (uspto.gov) 2026-07-18.
Keep every citation accurate — a wrong standard is worse than none.
"""

# statute key -> (one-paragraph standard with an actionable fix, MPEP citation)
STATUTES: dict[str, tuple[str, str]] = {
    "101": (
        "§101 subject-matter eligibility (Alice/Mayo two-step): a claim directed to an "
        "abstract idea (Step 2A Prong 1) that is not integrated into a practical application "
        "(Prong 2) and adds no inventive concept beyond well-understood, routine, conventional "
        "activity (Step 2B) is ineligible. Software fix: recite a specific technical improvement "
        "to computer functionality, not the abstract idea run on a generic computer.",
        "MPEP 2106",
    ),
    "102": (
        "§102 anticipation: a single prior-art reference disclosing — expressly or inherently — "
        "every claim limitation arranged as in the claim anticipates it. Fix: add a limitation "
        "no single reference discloses.",
        "MPEP 2131",
    ),
    "103": (
        "§103 obviousness (Graham / KSR): weigh the scope and content of the prior art, the "
        "differences from the claim, and the level of ordinary skill; a combination of known "
        "elements yielding predictable results is obvious absent a limitation with an unexpected "
        "result or no motivation to combine. Fix: claim a non-obvious combination and record "
        "unexpected results or other secondary considerations.",
        "MPEP 2141-2143",
    ),
    "112a": (
        "§112(a) written description & enablement: the specification must show possession of the "
        "full claimed scope and enable a skilled artisan to make and use it without undue "
        "experimentation (Wands factors). Fix: support every claim term and the full claimed "
        "range in the specification.",
        "MPEP 2163-2164",
    ),
    "112b": (
        "§112(b) definiteness (Nautilus 'reasonable certainty'): the claims must define scope with "
        "reasonable certainty; terms of degree ('substantially', 'about') need a benchmark, and "
        "every 'the'/'said' element needs antecedent basis. Fix: add antecedent basis and a "
        "definite standard for any relative term.",
        "MPEP 2173",
    ),
    "112f": (
        "§112(f) means-plus-function: 'means for [function]' — or a nonce word ('module', "
        "'mechanism', 'unit' for [function]) without recited structure — invokes §112(f) and is "
        "indefinite unless the specification discloses the corresponding structure (for a computer "
        "function, the specific algorithm). Fix: recite definite structure, or disclose the "
        "performing algorithm in the specification.",
        "MPEP 2181",
    ),
}


def reference_block() -> str:
    """The full reference, for injection into a drafting/critique/revise prompt.
    Deterministic (dict insertion order) so the prompt template hash is stable."""
    lines = [f"- {text} [{cite}]" for text, cite in STATUTES.values()]
    return (
        "PATENT-LAW STANDARDS (US MPEP) — apply these exactly; cite the section when you "
        "raise or fix a defect:\n" + "\n".join(lines)
    )
