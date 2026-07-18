"""Faithful printer of OpenShell CLI verbs + the Policy Advisor flow.

Every line is tagged [SIM]. OpenShell needs Linux Landlock/seccomp so it cannot
run on macOS; the verbs mirror research/nemoclaw-openshell.md §4/§6 exactly so
the demo reads like the real gateway. This is presentation, not enforcement —
the decision logic lives in containment/policy.py.
"""

BANNER = (
    "SIMULATION — OpenShell requires Linux (Landlock LSM + seccomp-BPF); it cannot "
    "run on macOS. Verbs and the Policy Advisor flow mirror "
    "research/nemoclaw-openshell.md §4/§6. Decisions come from the real "
    "inference/policy/airtight-sandbox.yaml via containment/policy.py."
)


def banner() -> None:
    print("=" * 78)
    print(BANNER)
    print("=" * 78)


def sim(line: str) -> None:
    print(f"  [SIM] {line}")


def denied_403(host: str, method: str, path: str, guidance: str) -> None:
    sim(f"{method} https://{host}{path}")
    sim(f"openshell gateway -> 403 default-deny")
    sim(f"    agent_guidance: {guidance}")
    sim(f"    next_steps: read /etc/openshell/skills/policy_advisor.md")


def hard_denied(host: str, method: str, path: str, reason: str) -> None:
    sim(f"{method} https://{host}{path}")
    sim(f"openshell gateway -> 403 HARD-DENY (matched deny_rule)")
    sim(f"    reason: {reason}")


def proposal_flow(chunk_id: str, reject_reason: str) -> None:
    sim(f"agent: POST policy.local/v1/proposals  (op=addRule)  -> chunk_id={chunk_id}")
    sim(f"agent: GET  policy.local/v1/proposals/{chunk_id}/wait?timeout=300")
    sim(f"operator (out-of-band): openshell rule get airtight --status pending")
    sim(f"operator: openshell rule reject airtight --chunk-id {chunk_id} \\")
    sim(f'              --reason \"{reject_reason}\"')
    sim(f"gateway -> proposal {chunk_id}: rejected")
    sim(f"    rejection_reason: {reject_reason}")
    sim(f"    validation_result: credential_reach_expansion")
    sim(f"agent: egress remains denied; disclosure never leaves the sandbox")
