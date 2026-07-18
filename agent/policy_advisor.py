"""Agent-side Policy Advisor client (G1) — the counterpart to OpenShell's F6.

When the sandbox gateway default-denies an egress (403), the agent doesn't just
fail: it reads the Policy Advisor skill, submits a narrow `addRule` proposal via
`policy.local`, and blocks on the operator's out-of-band decision (approve →
retry, reject → surface the reason). Mirrors research/nemoclaw-openshell.md §4.

The transport is injectable so this runs against a mock today (no OpenShell) and
the real `policy.local` gateway when F5 lands — the agent logic is identical.
"""

from dataclasses import dataclass, field
from typing import Protocol

from containment.policy import Decision, PolicyResult


@dataclass
class Proposal:
    chunk_id: str
    op: str  # "addRule"
    rule: dict  # the narrow rule the agent asks for
    status: str = "pending"  # pending | approved | rejected
    rejection_reason: str | None = None
    validation_result: str | None = None


class Transport(Protocol):
    def submit(self, proposal: Proposal) -> Proposal: ...
    def wait(self, chunk_id: str, timeout: int = 300) -> Proposal: ...


@dataclass
class MockTransport:
    """Stand-in for policy.local until F5. The operator decision is scripted so
    the demo is deterministic; default is to REJECT (the 'no external backup of
    client IP' beat)."""

    approve: bool = False
    reason: str = "no external backup of client IP"
    validation: str = "credential_reach_expansion"
    submitted: list = field(default_factory=list)

    def submit(self, proposal: Proposal) -> Proposal:
        self.submitted.append(proposal)
        return proposal

    def wait(self, chunk_id: str, timeout: int = 300) -> Proposal:
        prop = next(p for p in self.submitted if p.chunk_id == chunk_id)
        if self.approve:
            prop.status = "approved"
        else:
            prop.status, prop.rejection_reason, prop.validation_result = (
                "rejected", self.reason, self.validation)
        return prop


class PolicyAdvisorClient:
    def __init__(self, transport: Transport):
        self.transport = transport
        self._n = 0

    def escalate(self, denial: PolicyResult) -> Proposal:
        """Turn a default-deny into an addRule proposal and await the operator.
        HARD_DENY is never escalated — the caller shouldn't call us for it."""
        if denial.decision is Decision.HARD_DENY:
            raise ValueError("hard-deny is not escalable — no proposal submitted")
        self._n += 1
        proposal = Proposal(
            chunk_id=f"prop-{self._n:04d}",
            op="addRule",
            rule={"host": denial.host, "method": denial.method, "path": denial.path,
                  "allow": True},
        )
        self.transport.submit(proposal)
        return self.transport.wait(proposal.chunk_id)

    def retry_allowed(self, proposal: Proposal) -> bool:
        return proposal.status == "approved"
