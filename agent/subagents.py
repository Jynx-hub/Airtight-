"""Concurrent prior-art retrieval sub-agents — the vLLM continuous-batching workload.

The heartbeat fans out one Nano-tier sub-agent per retrieved loophole; they run
concurrently and each assesses how its loophole applies to the disclosure. This
is exactly the many-small-concurrent-requests pattern vLLM's continuous batching
is built for (JUDGING-RUBRIC vLLM bounty). Every sub-agent calls through the
doorway, so HiddenLayer analyzes all 2*N hops.
"""

from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass

from airtight import Disclosure, LoopholeRecord, call_model, config

ASSESS_SYSTEM = (
    "You are a prior-art retrieval sub-agent (Nano tier). Assess in one or two "
    "sentences how the single loophole below applies to the disclosed invention, "
    "and what claim language would foreclose it. Be terse."
)


@dataclass
class RetrievalNote:
    loophole_id: str
    assessment: str
    mode: str


def _assess(disclosure: Disclosure, loophole: LoopholeRecord, **gen_kwargs) -> RetrievalNote:
    user = (
        f"DISCLOSURE\n{disclosure.title}: {disclosure.summary}\n\n"
        f"LOOPHOLE\npattern: {loophole.pattern}\nclaim shape: {loophole.claim_shape}\n"
        f"remedy: {loophole.remedy}"
    )
    reply = call_model(
        [{"role": "system", "content": ASSESS_SYSTEM}, {"role": "user", "content": user}],
        role="tool",  # Nano reasoning-off tier
        **gen_kwargs,
    )
    return RetrievalNote(loophole_id=loophole.id, assessment=reply.text, mode=reply.mode)


def fan_out_retrieval(
    disclosure: Disclosure,
    retrieved: list[LoopholeRecord],
    max_workers: int | None = None,
    **gen_kwargs,
) -> list[RetrievalNote]:
    """One concurrent sub-agent per retrieved loophole. Results are assembled in
    retrieved order after join (deterministic — no in-thread mutation)."""
    if not retrieved:
        return []
    workers = min(max_workers or config.SUBAGENT_MAX_WORKERS, len(retrieved))
    with ThreadPoolExecutor(max_workers=workers) as pool:
        notes = list(pool.map(lambda lh: _assess(disclosure, lh, **gen_kwargs), retrieved))
    return notes


def notes_block(notes: list[RetrievalNote]) -> str:
    if not notes:
        return ""
    lines = "\n".join(f"- [{n.loophole_id}] {n.assessment}" for n in notes)
    return f"\n\nPrior-art assessments from retrieval sub-agents:\n{lines}"
