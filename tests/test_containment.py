"""M5/M6 containment tests — decision logic driven by the real policy YAML."""

import pathlib

import pytest
import yaml

from airtight import config
from airtight import guardrails as g
from containment.policy import Decision, decide

ROOT = pathlib.Path(__file__).resolve().parent.parent
POLICY = ROOT / "inference" / "policy" / "airtight-sandbox.yaml"


def d(host, method, path, **kw):
    return decide("egress", host, method, path, policy_path=POLICY, **kw)


def test_filing_post_is_hard_denied():
    assert d("api.uspto.gov", "POST", "/filings/submit").decision is Decision.HARD_DENY


def test_search_get_is_allowed():
    assert d("api.uspto.gov", "GET", "/search/patents").decision is Decision.ALLOW
    assert d("data.uspto.gov", "GET", "/anything/here").decision is Decision.ALLOW


def test_unknown_host_escalates():
    r = d("api.dropboxapi.com", "POST", "/2/files/upload")
    assert r.decision is Decision.DEFAULT_DENY_ESCALATE
    assert r.agent_guidance


def test_matched_host_unmatched_rule_escalates():
    # filing_api host matched, but POST to a non-denied non-allowed path
    assert d("api.uspto.gov", "POST", "/other").decision is Decision.DEFAULT_DENY_ESCALATE


def test_search_glob_does_not_match_filing_path():
    # the /search/** allow must NOT leak to /filings/submit
    assert d("api.uspto.gov", "POST", "/filings/submit").decision is Decision.HARD_DENY


def test_decision_is_data_driven(tmp_path):
    """Editing the YAML deny_rule flips the decision — proves it reads the file."""
    policy = yaml.safe_load(POLICY.read_text())
    policy["network_policies"]["filing_api"]["endpoints"][0]["deny_rules"] = []
    edited = tmp_path / "edited.yaml"
    edited.write_text(yaml.safe_dump(policy))
    # with the deny_rule gone, the filing POST falls through to default-deny, not hard-deny
    assert decide("egress", "api.uspto.gov", "POST", "/filings/submit",
                  policy_path=edited).decision is Decision.DEFAULT_DENY_ESCALATE


def test_audit_override_allows_with_log():
    r = d("api.dropboxapi.com", "POST", "/x", enforcement_override="audit")
    # unknown host still escalates (no endpoint to audit); matched-but-unruled would allow
    assert r.decision is Decision.DEFAULT_DENY_ESCALATE
    r2 = d("api.uspto.gov", "POST", "/other", enforcement_override="audit")
    assert r2.decision is Decision.ALLOW


def test_demo_wall_holds():
    from containment.demo import main

    assert main() == 0


# --- A3: the demo drives the REAL PolicyAdvisorClient, not hardcoded prints ---

def test_hard_deny_is_never_escalated():
    """Filing is hard-denied — attempt_egress must NOT submit a proposal for it."""
    from agent.policy_advisor import MockTransport, PolicyAdvisorClient
    from containment.demo import attempt_egress

    transport = MockTransport()
    outcome = attempt_egress("api.uspto.gov", "POST", "/filings/submit", "xml",
                             PolicyAdvisorClient(transport))
    assert outcome == "hard-denied"
    assert transport.submitted == []  # escalate() was never called


def test_default_deny_escalates_via_real_client_and_operator_rejects():
    from agent.policy_advisor import MockTransport, PolicyAdvisorClient
    from containment.demo import attempt_egress

    transport = MockTransport(approve=False)
    outcome = attempt_egress("api.dropboxapi.com", "POST", "/2/files/upload", "bytes",
                             PolicyAdvisorClient(transport))
    assert "rejected" in outcome
    assert len(transport.submitted) == 1 and transport.submitted[0].op == "addRule"


def test_approved_escalation_retries_and_sends():
    """The operator-approve branch is a real path the demo exercises, not just a test."""
    from agent.policy_advisor import MockTransport, PolicyAdvisorClient
    from containment.demo import attempt_egress

    transport = MockTransport(approve=True)
    outcome = attempt_egress("api.patentsview.org", "GET", "/patents/query", "q=g06n",
                             PolicyAdvisorClient(transport))
    assert outcome == "sent"
    assert len(transport.submitted) == 1  # escalated, then approved → retried


# --- A6: the fusion — policy ALLOWs, HiddenLayer still acts, on ONE action ---

def test_allow_action_still_crosses_hiddenlayer_and_quarantines(monkeypatch):
    """The 'one boundary' claim: an action policy ALLOWs is independently gated by
    HiddenLayer on the tool_result hop. Reachable AND observable, not dead code."""
    from containment.demo import _read_vault

    # gate 1: policy allows the read
    assert d("vault.internal", "GET", "/disclosures/disc-0001").decision is Decision.ALLOW

    # gate 2: HiddenLayer quarantines the returned disclosure bytes
    monkeypatch.setattr(config, "HL_ENABLED", True)
    monkeypatch.setattr(g, "_raw_analyze",
                        lambda text, phase: {"metadata": {"event_id": "e"},
                                             "analysis": [{"name": "pii", "phase": phase,
                                                           "detected": "CONFIDENTIAL" in text,
                                                           "findings": {"matches": []}}]})
    assert _read_vault("/disclosures/disc-0001") == g.QUARANTINE_PLACEHOLDER


def test_guarded_egress_blocks_pii_in_body(monkeypatch):
    monkeypatch.setattr(config, "HL_ENABLED", True)
    monkeypatch.setattr(g, "_raw_analyze",
                        lambda text, phase: {"metadata": {"event_id": "e"},
                                             "analysis": [{"name": "pii", "phase": "input", "detected": True,
                                                           "findings": {"matches": []}}]})

    @g.guarded_tool
    def send(dest, payload):
        return "sent"

    with pytest.raises(g.GuardrailBlocked):
        send("api.dropboxapi.com", "CONFIDENTIAL disclosure bytes")
