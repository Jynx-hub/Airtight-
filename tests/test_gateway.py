"""A4: inference.local gateway wiring — hermetic (no sockets, no network).

The full three-process end-to-end proof (dummy token rejected direct / accepted
via gateway / key host-side only) lives in runtime/gateway_smoke.py, kept out of
the suite so `pytest tests/` stays server-free. These cover the config wiring."""

import pytest

from runtime import inference_gateway
from runtime.inference_local import _resolve


def _clear_backend_env(monkeypatch):
    for k in ("INFERENCE_BACKEND", "INFERENCE_GATEWAY_URL", "INFERENCE_BASE_URL",
              "INFERENCE_MODEL", "INFERENCE_API_KEY", "MODAL_BASE_URL", "MODAL_API_KEY",
              "MODAL_MODEL", "NVIDIA_API_KEY"):
        monkeypatch.delenv(k, raising=False)


def test_gateway_backend_points_agent_at_gateway_with_dummy_key(monkeypatch):
    """INFERENCE_BACKEND=gateway → the agent resolves to the gateway URL and a dummy
    token. No provider key is read on the sandbox side — that is the A4 close."""
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("INFERENCE_BACKEND", "gateway")
    monkeypatch.setenv("INFERENCE_GATEWAY_URL", "http://inference.local/v1")

    base, model, key = _resolve()
    assert base == "http://inference.local/v1"
    assert key == "sandbox-no-cred"  # dummy — the real key never lives here
    assert model == "nemotron"


def test_gateway_refuses_to_front_itself(monkeypatch):
    """The gateway's own backend must be the upstream, not 'gateway' — else it would
    forward to itself. resolve_upstream() catches the loop."""
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("INFERENCE_BACKEND", "gateway")
    with pytest.raises(RuntimeError, match="forward to itself"):
        inference_gateway.resolve_upstream()


def test_gateway_resolves_operator_upstream_from_the_one_table(monkeypatch):
    """The gateway reuses inference_local._resolve() — the single backend table —
    so INFERENCE_BACKEND=modal picks the operator's real destination + key."""
    _clear_backend_env(monkeypatch)
    monkeypatch.setenv("INFERENCE_BACKEND", "modal")
    monkeypatch.setenv("MODAL_BASE_URL", "http://127.0.0.1:9/v1")
    monkeypatch.setenv("MODAL_API_KEY", "real-provider-key")
    monkeypatch.setenv("MODAL_MODEL", "nemotron")

    base, model, key = inference_gateway.resolve_upstream()
    assert base == "http://127.0.0.1:9/v1"
    assert key == "real-provider-key"
    assert model == "nemotron"


def test_mask_never_reveals_the_key():
    assert inference_gateway._mask("supersecretkey") == "<set:14ch>"
    assert inference_gateway._mask("") == "<empty>"
