"""Agent-side Policy Advisor client (G1): 403 -> addRule proposal -> operator decision."""

import pytest

from agent.policy_advisor import MockTransport, PolicyAdvisorClient, Proposal
from containment.policy import Decision, PolicyResult, decide

POLICY = "inference/policy/airtight-sandbox.yaml"


def test_default_deny_escalates_and_operator_rejects():
    denial = decide("egress", "api.dropboxapi.com", "POST", "/2/files/upload", policy_path=POLICY)
    assert denial.decision is Decision.DEFAULT_DENY_ESCALATE  # the Dropbox exfil

    client = PolicyAdvisorClient(MockTransport(approve=False))
    outcome = client.escalate(denial)
    assert outcome.status == "rejected"
    assert outcome.rejection_reason == "no external backup of client IP"
    assert outcome.validation_result == "credential_reach_expansion"
    assert not client.retry_allowed(outcome)  # egress never proceeds


def test_operator_approve_allows_retry():
    denial = PolicyResult(Decision.DEFAULT_DENY_ESCALATE, "api.example.com", "GET", "/new")
    client = PolicyAdvisorClient(MockTransport(approve=True))
    outcome = client.escalate(denial)
    assert outcome.status == "approved"
    assert client.retry_allowed(outcome)


def test_hard_deny_is_not_escalable():
    denial = decide("egress", "api.uspto.gov", "POST", "/filings/submit", policy_path=POLICY)
    assert denial.decision is Decision.HARD_DENY  # irreversible filing
    with pytest.raises(ValueError, match="not escalable"):
        PolicyAdvisorClient(MockTransport()).escalate(denial)


def test_proposal_is_narrow_and_recorded():
    denial = PolicyResult(Decision.DEFAULT_DENY_ESCALATE, "h", "POST", "/p")
    transport = MockTransport()
    PolicyAdvisorClient(transport).escalate(denial)
    assert len(transport.submitted) == 1
    prop = transport.submitted[0]
    assert prop.op == "addRule" and prop.rule["host"] == "h"
