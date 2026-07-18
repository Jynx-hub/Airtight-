"""Policy decisions from the real OpenShell YAML (M5).

decide() parses inference/policy/airtight-sandbox.yaml and returns the three-tier
gradient: reversible → ALLOW, irreversible → HARD_DENY, ambiguous → default-deny
that escalates to the Policy Advisor human loop (research/nemoclaw-openshell.md
§4-§5). Decisions come from the file, not hardcoded rules — editing a deny_rule
in the YAML flips the decision (proven by test).

OpenShell itself needs Linux (Landlock + seccomp) so it can't run on macOS; this
is a faithful decision model of the network tier, not the enforcer.
"""

from dataclasses import dataclass
from enum import Enum
from pathlib import Path

import yaml

DEFAULT_POLICY = "inference/policy/airtight-sandbox.yaml"


class Decision(str, Enum):
    ALLOW = "allow"  # reversible, auto
    HARD_DENY = "hard_deny"  # irreversible, matched deny_rule — not escalable
    DEFAULT_DENY_ESCALATE = "default_deny_escalate"  # ambiguous — Policy Advisor HITL


@dataclass
class PolicyResult:
    decision: Decision
    host: str
    method: str
    path: str
    matched_policy: str | None = None
    matched_rule: str | None = None
    reason: str | None = None
    agent_guidance: str | None = None


def _host_matches(rule_host: str, host: str) -> bool:
    return host == rule_host or host.endswith("." + rule_host)


def _path_matches(pattern: str, path: str) -> bool:
    if pattern in ("/**", "**"):
        return True
    if pattern.endswith("/**"):
        return path.startswith(pattern[:-3] + "/") or path == pattern[:-3]
    if pattern.endswith("/*"):
        prefix = pattern[:-2]
        rest = path[len(prefix):].lstrip("/")
        return path.startswith(prefix) and "/" not in rest and rest != ""
    return pattern == path


def decide(
    action: str,
    host: str,
    method: str,
    path: str,
    *,
    policy_path: str | Path = DEFAULT_POLICY,
    enforcement_override: str = "enforce",
) -> PolicyResult:
    policy = yaml.safe_load(Path(policy_path).read_text())
    method = method.upper()

    for name, spec in (policy.get("network_policies") or {}).items():
        for ep in spec.get("endpoints", []):
            if not _host_matches(ep.get("host", ""), host):
                continue

            # Tier 3: irreversible hard-deny (matched deny_rule) — never escalable.
            for deny in ep.get("deny_rules", []):
                if deny.get("method", method).upper() == method and _path_matches(deny.get("path", "/**"), path):
                    return PolicyResult(
                        Decision.HARD_DENY, host, method, path, matched_policy=name,
                        matched_rule=f"deny {deny.get('method')} {deny.get('path')}",
                        reason="irreversible action denied by policy; cannot be escalated",
                    )

            # Tier 1: reversible allow.
            for rule in ep.get("rules", []):
                allow = rule.get("allow", {})
                if allow.get("method", method).upper() == method and _path_matches(allow.get("path", "/**"), path):
                    return PolicyResult(
                        Decision.ALLOW, host, method, path, matched_policy=name,
                        matched_rule=f"allow {allow.get('method')} {allow.get('path')}",
                    )

            # access grant (e.g. client_datastore read-only): reads allowed, writes not.
            access = ep.get("access")
            if access in ("read-only", "read-write", "full"):
                reading = method in ("GET", "HEAD")
                if reading or access in ("read-write", "full"):
                    return PolicyResult(
                        Decision.ALLOW, host, method, path, matched_policy=name,
                        matched_rule=f"access: {access}",
                    )

            # Endpoint matched but no rule matched. enforcement_override models the
            # operator's audit->enforce flip and takes precedence over the YAML's
            # shipped `enforcement:` (which starts at audit for discovery).
            if enforcement_override == "audit":
                return PolicyResult(
                    Decision.ALLOW, host, method, path, matched_policy=name,
                    matched_rule="audit mode (observe, don't block)",
                )
            return PolicyResult(
                Decision.DEFAULT_DENY_ESCALATE, host, method, path, matched_policy=name,
                agent_guidance="no matching allow rule; submit an addRule proposal to the Policy Advisor",
            )

    # Tier 2: host matches no endpoint → default-deny → escalate.
    return PolicyResult(
        Decision.DEFAULT_DENY_ESCALATE, host, method, path,
        agent_guidance=f"host {host} is not on any egress allowlist; submit an addRule proposal",
    )
