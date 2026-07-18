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


def proposal(prop) -> None:
    """Render a REAL agent.policy_advisor.Proposal — the object the injectable
    PolicyAdvisorClient returned, not a hardcoded string. Both operator decisions
    (approve/reject) render from the same object, so what the demo prints is
    exactly what the escalation client produced."""
    rule = prop.rule
    sim(f"agent: POST policy.local/v1/proposals  (op={prop.op})  -> chunk_id={prop.chunk_id}")
    sim(f"    proposed rule: allow {rule.get('method')} {rule.get('host')}{rule.get('path')}")
    sim(f"agent: GET  policy.local/v1/proposals/{prop.chunk_id}/wait?timeout=300")
    sim(f"operator (out-of-band): openshell rule get airtight --status pending")
    if prop.status == "approved":
        sim(f"operator: openshell rule approve airtight --chunk-id {prop.chunk_id}")
        sim(f"gateway -> proposal {prop.chunk_id}: approved; policy hot-reloaded")
        sim(f"agent: rule now allows it — retrying the egress")
    else:
        sim(f"operator: openshell rule reject airtight --chunk-id {prop.chunk_id} \\")
        sim(f'              --reason \"{prop.rejection_reason}\"')
        sim(f"gateway -> proposal {prop.chunk_id}: rejected")
        sim(f"    rejection_reason: {prop.rejection_reason}")
        sim(f"    validation_result: {prop.validation_result}")
        sim(f"agent: egress remains denied; disclosure never leaves the sandbox")
