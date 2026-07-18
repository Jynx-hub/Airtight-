"""Offline end-to-end proof for the inference.local gateway (A4). NO GPU, NO credits.

Stands up three roles as separate processes so the credential boundary is real, not
a same-process claim:

  provider (runtime/mock_endpoint.py)  — the upstream, requires the REAL key
  gateway  (runtime/inference_gateway) — host-side, HOLDS the real key, injects it
  agent    (this driver)               — sandbox role, holds ONLY a dummy token

Then it asserts the two properties A4 is supposed to deliver:

  1. The sandbox credential is useless on its own — the dummy token talking to the
     provider DIRECTLY is rejected (401).
  2. The gateway injects the real key host-side — the SAME dummy token works through
     the gateway (200), and the model is pinned by the operator (the agent's attempt
     to choose a different model is overridden).

Run:  python -m runtime.gateway_smoke     (or: python runtime/gateway_smoke.py)
"""
from __future__ import annotations

import json
import os
import secrets
import socket
import subprocess
import sys
import time
from urllib import error as urlerror
from urllib import request as urlrequest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DUMMY = "sandbox-no-cred"  # the only token the agent/sandbox ever holds


def _free_port() -> int:
    s = socket.socket()
    s.bind(("127.0.0.1", 0))
    port = s.getsockname()[1]
    s.close()
    return port


def _post(url: str, key: str, body: dict, stream: bool = False):
    data = json.dumps(body).encode()
    req = urlrequest.Request(
        url, data=data, method="POST",
        headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
    )
    try:
        resp = urlrequest.urlopen(req, timeout=30)
    except urlerror.HTTPError as exc:
        return exc.code, exc.read().decode()
    if stream:
        return resp.status, b"".join(resp).decode()
    return resp.status, resp.read().decode()


def _wait_ready(url: str, key: str, label: str, tries: int = 100) -> None:
    for _ in range(tries):
        try:
            req = urlrequest.Request(url, headers={"Authorization": f"Bearer {key}"})
            urlrequest.urlopen(req, timeout=2).read()
            return
        except urlerror.HTTPError:
            return  # answered (even 401/404) → it's up
        except (urlerror.URLError, ConnectionError, OSError):
            time.sleep(0.1)
    raise RuntimeError(f"{label} did not come up at {url}")


def main() -> int:
    real_key = "provider-" + secrets.token_hex(12)  # the operator's provider key
    assert real_key not in os.environ.values(), "test key must not be in the agent env"

    provider_port, gateway_port = _free_port(), _free_port()
    provider = f"http://127.0.0.1:{provider_port}/v1"
    gateway = f"http://127.0.0.1:{gateway_port}/v1"

    # provider env is bare; the real key is passed as an ARG (its own credential)
    provider_proc = subprocess.Popen(
        [sys.executable, os.path.join(ROOT, "runtime", "mock_endpoint.py"),
         "--port", str(provider_port), "--api-key", real_key],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT,
    )
    # gateway env HOLDS the real key (host-side) and points upstream at the provider
    gw_env = {**os.environ, "INFERENCE_BACKEND": "modal",
              "MODAL_BASE_URL": provider, "MODAL_API_KEY": real_key, "MODAL_MODEL": "nemotron"}
    gateway_proc = subprocess.Popen(
        [sys.executable, "-m", "runtime.inference_gateway", "--port", str(gateway_port)],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, cwd=ROOT, env=gw_env,
    )

    failures: list[str] = []
    try:
        _wait_ready(f"{provider}/models", real_key, "provider")
        _wait_ready(f"http://127.0.0.1:{gateway_port}/healthz", DUMMY, "gateway")

        chat = {"model": "agent-tried-to-pick-this-model",
                "messages": [{"role": "user", "content": "Reply with exactly: AIRTIGHT-OK"}],
                "max_tokens": 4}

        # (1) the sandbox's dummy token is useless talking to the provider directly
        status, _ = _post(f"{provider}/chat/completions", DUMMY, chat)
        if status == 401:
            print("✔ [1] agent's dummy token → provider DIRECTLY: 401 rejected "
                  "(the sandbox holds no usable credential)")
        else:
            failures.append(f"[1] expected 401 direct-to-provider with dummy token, got {status}")

        # (2) the same dummy token works through the gateway — key injected host-side
        status, text = _post(f"{gateway}/chat/completions", DUMMY, chat)
        body = json.loads(text) if status == 200 else {}
        content = (body.get("choices", [{}])[0].get("message", {}) or {}).get("content", "")
        model = body.get("model")
        if status == 200 and "AIRTIGHT-OK" in content:
            print("✔ [2] agent's dummy token → GATEWAY: 200 OK "
                  "(gateway stripped the dummy and injected the real key host-side)")
        else:
            failures.append(f"[2] expected 200 + AIRTIGHT-OK via gateway, got {status}: {text[:120]}")

        # (3) the operator's model is pinned — the agent could not choose its own
        if model == "nemotron":
            print("✔ [3] model pinned to operator's 'nemotron' (agent asked for "
                  "'agent-tried-to-pick-this-model' — overridden)")
        else:
            failures.append(f"[3] expected model pinned to 'nemotron', got {model!r}")

        # (4) streaming pass-through works through the gateway
        status, stext = _post(f"{gateway}/chat/completions", DUMMY,
                              {**chat, "stream": True}, stream=True)
        if status == 200 and "data:" in stext and "[DONE]" in stext:
            print("✔ [4] streaming (SSE) proxied through the gateway to completion")
        else:
            failures.append(f"[4] streaming pass-through failed: status={status}")

        # (5) the real key never appears in the agent's environment
        if not any(real_key in v for v in os.environ.values()):
            print("✔ [5] the provider key is absent from the agent's environment "
                  "(it lives only in the gateway process)")
        else:
            failures.append("[5] provider key leaked into the agent environment")
    finally:
        for p in (gateway_proc, provider_proc):
            p.terminate()
            try:
                p.wait(timeout=5)
            except subprocess.TimeoutExpired:
                p.kill()

    if failures:
        print("\n✗ FAIL:")
        for f in failures:
            print(f"    {f}")
        return 1
    print("\n✔ PASS — inference.local gateway injects creds host-side; the sandbox holds none.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
