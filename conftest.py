"""Put the repo root on sys.path for the test run.

The installed packages (airtight, agent, containment, surface) import via the
editable install, but `runtime/` is an operator-scripts dir that is deliberately
not packaged — yet `runtime.inference_local` / `runtime.inference_gateway` are
importable modules (run as `python -m runtime.x` from the repo root). This makes
that same namespace import resolve under pytest, without repackaging runtime/.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


@pytest.fixture(autouse=True)
def _isolate_security_log(tmp_path, monkeypatch):
    """Never let a test append to `results/security/`.

    `analyze` returns early when `HL_ENABLED` is false, so a plain run is safe — but
    the guardrail tests call `hl_on()` with a fixture `_raw_analyze`, which takes the
    full path through `_persist`. Those files are what the demo and the audit read as
    *evidence*, and a fixture hop in them is indistinguishable from a real AIDR one
    without inspecting every event_id. Before this fixture, one `pytest` run appended
    ~127 fake hops; the log stood at 257 hops with **zero** real UUIDs.
    """
    from airtight import guardrails

    monkeypatch.setattr(guardrails, "_SECURITY_DIR", tmp_path / "security")


@pytest.fixture(autouse=True)
def _no_live_hiddenlayer(monkeypatch):
    """The suite is "stub mode, no network" — hold that even with real HL creds.

    `config.py` loads `.env`, so the moment an operator puts working HiddenLayer
    credentials there with `AIRTIGHT_HL_ENABLED=true` (which the live demo needs),
    every `analyze` call in the suite becomes a real AIDR round-trip: `test_surface.py`
    went from 34 passed in 1.8s to 2 failed in 70s, and the failures were the bus
    correctly acting on live detections the fixtures never predicted.

    This is the same shape as [[test-asserting-a-credential-is-absent-is-a-live-call]]:
    a suite that is green only on a machine *without* the key. Tests that want the bus
    opt in explicitly via `hl_on()`, which sets the flag and stubs `_raw_analyze`
    together — so pinning the default to False here cannot mask a real behaviour.
    """
    from airtight import config

    monkeypatch.setattr(config, "HL_ENABLED", False)


@pytest.fixture(autouse=True)
def _isolate_episode_writes(tmp_path, monkeypatch):
    """Never let a test append to `memory/episodes/`.

    Same hazard as the security log above, and the same shape: the surface's
    product path now passes an `episode_sink`, so with `AIRTIGHT_EPISODES_ENABLED`
    true in the operator's `.env` — which `config.py` loads — every test that
    drafts would mint a real episode into the tree. Those files are memory the
    next draft retrieves and the /admin panel counts; a suite-generated one is
    indistinguishable from a demo-generated one on disk. The flag is deliberately
    left alone: what a test run must not do is *write*, and pinning the directory
    keeps the gate itself under test (tests/test_episodes.py flips the flag).
    """
    from airtight import config

    monkeypatch.setattr(config, "EPISODES_DIR", str(tmp_path / "episodes"))
