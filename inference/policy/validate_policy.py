"""A2 — structural validation of the OpenShell policy YAML.

Validates the artifact against the four-tier schema we can check offline: filesystem /
process / network tiers are present and well-formed, every endpoint has a valid
`enforcement:` mode, rules/deny_rules are well-shaped, and the inference hop exists. This
is the LOCAL half of A2's "validation"; the live early-preview schema check still happens
on DGX Spark (inference/policy/ONBOARDING.md "Things to confirm").

    python -m inference.policy.validate_policy [path]     # exit 0 clean, 1 with errors
"""
from __future__ import annotations

import sys
from pathlib import Path

import yaml

DEFAULT = "inference/policy/airtight-sandbox.yaml"
_MODES = {"audit", "enforce"}
_METHODS = {"GET", "HEAD", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"}


def validate(policy: dict) -> list[str]:
    """Return a list of human-readable problems ([] means valid)."""
    errs: list[str] = []

    # tiers that must exist
    for tier in ("filesystem_policy", "process", "network_policies"):
        if tier not in policy:
            errs.append(f"missing required tier: {tier}")

    proc = policy.get("process") or {}
    if proc.get("run_as_user") in (None, "root"):
        errs.append("process.run_as_user must be set and non-root")

    nps = policy.get("network_policies") or {}
    if not nps:
        errs.append("network_policies is empty")

    for name, spec in nps.items():
        eps = (spec or {}).get("endpoints")
        if not isinstance(eps, list) or not eps:
            errs.append(f"{name}: endpoints must be a non-empty list")
            continue
        for i, ep in enumerate(eps):
            where = f"{name}.endpoints[{i}]"
            if not ep.get("host"):
                errs.append(f"{where}: missing host")
            mode = ep.get("enforcement")
            if mode not in _MODES:
                errs.append(f"{where}: enforcement must be one of {sorted(_MODES)}, got {mode!r}")
            for kind in ("rules", "deny_rules"):
                for j, rule in enumerate(ep.get(kind) or []):
                    spec_rule = rule.get("allow", rule) if kind == "rules" else rule
                    m = spec_rule.get("method")
                    if m is not None and m.upper() not in _METHODS:
                        errs.append(f"{where}.{kind}[{j}]: bad method {m!r}")
                    if not spec_rule.get("path"):
                        errs.append(f"{where}.{kind}[{j}]: missing path")
            if "access" in ep and ep["access"] not in ("read-only", "read-write", "full"):
                errs.append(f"{where}: bad access {ep['access']!r}")

    # inference tier must exist (the one operator-pinned hop)
    hosts = {ep.get("host") for spec in nps.values() for ep in (spec or {}).get("endpoints", [])}
    if "inference.local" not in hosts:
        errs.append("no inference.local endpoint — the pinned inference hop is missing")

    return errs


def validate_file(path: str | Path = DEFAULT) -> list[str]:
    return validate(yaml.safe_load(Path(path).read_text()))


def main() -> int:
    path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT
    errs = validate_file(path)
    if errs:
        print(f"✗ {path}: {len(errs)} problem(s)")
        for e in errs:
            print(f"    - {e}")
        return 1
    print(f"✔ {path}: structurally valid (four tiers, enforcement modes, inference hop). "
          "Live-schema check remains on DGX.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
