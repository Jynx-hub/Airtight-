"""A2: structural validation of the OpenShell policy YAML (the local half; live-schema is DGX)."""

import pathlib

from inference.policy.validate_policy import validate, validate_file

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY = ROOT / "inference" / "policy" / "airtight-sandbox.yaml"


def test_shipped_policy_is_structurally_valid():
    assert validate_file(POLICY) == []


def test_validator_catches_bad_enforcement_and_missing_inference_hop():
    bad = {"filesystem_policy": {}, "process": {"run_as_user": "agent"},
           "network_policies": {"x": {"endpoints": [{"host": "h", "enforcement": "log"}]}}}
    errs = validate(bad)
    assert any("enforcement must be one of" in e for e in errs)
    assert any("inference.local" in e for e in errs)


def test_validator_flags_root_process():
    bad = {"filesystem_policy": {}, "process": {"run_as_user": "root"},
           "network_policies": {"ig": {"endpoints": [{"host": "inference.local", "enforcement": "enforce"}]}}}
    assert any("non-root" in e for e in validate(bad))
