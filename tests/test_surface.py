"""Applicant Surface API tests — stub mode, no network.

Skipped if fastapi isn't installed, so a `.[dev]`-only clone stays green;
install with `.[web]` to exercise them.
"""

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from airtight import config  # noqa: E402
from airtight import guardrails as g  # noqa: E402
from surface.app import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def force_stub(monkeypatch):
    monkeypatch.setattr(config, "MODE", "stub")
    g.AUDIT_LOG.clear()  # module global — other test files leave entries in it


def test_health_reports_mode():
    body = client.get("/api/health").json()
    assert body["mode"] == "stub" and body["model"]


def test_sample_is_a_valid_disclosure():
    body = client.get("/api/sample").json()
    assert body["id"] and body["technology_class"] and body["details"]


def test_index_serves_html():
    res = client.get("/")
    assert res.status_code == 200 and "Airtight" in res.text


def test_draft_returns_draft_and_report():
    disclosure = client.get("/api/sample").json()
    res = client.post("/api/draft", json=disclosure)
    assert res.status_code == 200
    body = res.json()
    assert body["draft"]["disclosure_id"] == disclosure["id"]
    assert len(body["draft"]["claims"]) >= 2
    # report exists; security scanning off in stub mode (honest, not faked)
    assert body["report"]["security_scanning"] is False
    assert body["report"]["security_findings"] == []
    assert "smart_catches" in body["report"]
