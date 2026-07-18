"""Airtight runtime — the `inference.local` gateway (A4 / the code side of F5).

Closes the two honest gaps recorded in docs/INFERENCE-LOCAL.md §"Known gaps":

  1. `inference.local` becomes a resolvable host with a REAL process in front of
     it, not just a naming contract. The operator maps the name to this process
     (`127.0.0.1 inference.local` in /etc/hosts) and it answers OpenAI-compatible
     requests.
  2. Provider credentials live HOST-SIDE. The sandbox client sends a dummy token
     (`INFERENCE_BACKEND=gateway` → key `sandbox-no-cred`); THIS process strips it
     and injects the operator's real key before forwarding upstream. The agent
     never holds a usable credential — proven by runtime/gateway_smoke.py, where
     the same dummy token is rejected talking to the provider directly (401) yet
     works through the gateway (200).

It is a small, stdlib-only OpenAI-compatible reverse proxy. It resolves the
operator-pinned upstream with the SAME table as `inference_local._resolve()`
(one source of truth for "which backend"), so `INFERENCE_BACKEND=modal|nim` still
selects the destination — and it pins the model on the way through, so the agent
can override neither the endpoint nor the model. That is the design invariant
(docs/INFERENCE-LOCAL.md) enforced at a real hop instead of by convention.

Scope, honestly: this is the credential-injection + name-resolution half of F5.
The FULL containment story — a sandbox that provably cannot reach the host's env
by any other path — still needs OpenShell's Landlock + seccomp isolation (A1),
which needs Linux. This gateway does not, so it runs and is verifiable on any OS
against runtime/mock_endpoint.py at zero GPU cost.

Run (host side — holds the real key):
    INFERENCE_BACKEND=modal MODAL_BASE_URL=... MODAL_API_KEY=... \
        python -m runtime.inference_gateway --port 8900
Point the agent at it (sandbox side — holds NO key):
    INFERENCE_BACKEND=gateway INFERENCE_GATEWAY_URL=http://inference.local/v1
End-to-end offline proof (no GPU, no credits):
    python -m runtime.gateway_smoke
"""
from __future__ import annotations

import argparse
import json
import os
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib import error as urlerror
from urllib import request as urlrequest

VERBOSE = False
UPSTREAM_TIMEOUT = 900.0


def resolve_upstream() -> tuple[str, str, str]:
    """(base_url, model, key) for the operator-pinned upstream, resolved fresh per
    request so an operator env reload repoints the backend without a restart.

    Reuses inference_local._resolve() — the ONE backend table — and refuses the
    'gateway' backend, which would make the gateway forward to itself."""
    backend = os.environ.get("INFERENCE_BACKEND", "").strip().lower()
    if backend == "gateway":
        raise RuntimeError(
            "the gateway's own INFERENCE_BACKEND is 'gateway' — it would forward to "
            "itself. Set it to the UPSTREAM this gateway fronts: modal | nim | (unset=legacy)."
        )
    from runtime.inference_local import _resolve

    return _resolve()


def _mask(key: str) -> str:
    return f"<set:{len(key)}ch>" if key else "<empty>"


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, fmt: str, *args: object) -> None:
        if VERBOSE:
            super().log_message(fmt, *args)

    def _json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ── routes ──────────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        if self.path.rstrip("/").endswith("/healthz"):
            try:
                base, model, key = resolve_upstream()
            except Exception as exc:  # noqa: BLE001 — surface config errors as 500
                return self._json(500, {"status": "error", "error": str(exc)})
            return self._json(200, {
                "status": "ok",
                "backend": os.environ.get("INFERENCE_BACKEND") or "legacy",
                "upstream": base,
                "model": model,
                "upstream_key": _mask(key),  # never the value
                "note": "provider credential lives here (host-side); the sandbox holds none",
            })
        self._forward("GET", None)

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length", "0"))
        self._forward("POST", self.rfile.read(length) if length else b"")

    # ── the proxy hop ───────────────────────────────────────────────────────────
    def _forward(self, method: str, raw: bytes | None) -> None:
        try:
            base, model, key = resolve_upstream()
        except Exception as exc:  # noqa: BLE001
            return self._json(502, {"error": {"message": f"gateway upstream unresolved: {exc}"}})

        # Pin the operator's model on chat/completions; the agent cannot override it.
        is_chat = self.path.rstrip("/").endswith("/chat/completions")
        stream = False
        if raw:
            try:
                body = json.loads(raw)
                if isinstance(body, dict):
                    if is_chat or "model" in body:
                        body["model"] = model
                    stream = bool(body.get("stream"))
                    raw = json.dumps(body).encode()
            except json.JSONDecodeError:
                pass  # not JSON — forward untouched

        tail = self.path[len("/v1"):] if self.path.startswith("/v1/") else self.path
        upstream_url = base.rstrip("/") + tail

        # The credential injection: the inbound (dummy) Authorization is dropped and
        # the operator's real key is set here, host-side. The key never touches the
        # sandbox and is never logged.
        headers = {"Authorization": f"Bearer {key}"}
        data = None
        if method == "POST":
            headers["Content-Type"] = "application/json"
            data = raw or b"{}"

        req = urlrequest.Request(upstream_url, data=data, headers=headers, method=method)
        try:
            resp = urlrequest.urlopen(req, timeout=UPSTREAM_TIMEOUT)
        except urlerror.HTTPError as exc:  # upstream answered with an error — pass it through
            err_body = exc.read()
            self.send_response(exc.code)
            self.send_header("Content-Type", exc.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(err_body)))
            self.end_headers()
            self.wfile.write(err_body)
            return
        except urlerror.URLError as exc:  # upstream unreachable
            return self._json(502, {"error": {"message": f"gateway could not reach upstream {base}: {exc.reason}"}})

        ctype = resp.headers.get("Content-Type", "application/json")
        if stream or "text/event-stream" in ctype:
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Cache-Control", "no-cache")
            self.send_header("Transfer-Encoding", "chunked")
            self.end_headers()
            for line in resp:  # SSE is line-delimited — flush per line to preserve streaming
                self.wfile.write(b"%X\r\n" % len(line) + line + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        else:
            payload = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)


def build_server(host: str, port: int) -> ThreadingHTTPServer:
    srv = ThreadingHTTPServer((host, port), Handler)
    srv.daemon_threads = True
    return srv


def main() -> int:
    global VERBOSE, UPSTREAM_TIMEOUT
    ap = argparse.ArgumentParser(description="inference.local gateway — host-side credential injection")
    ap.add_argument("--host", default="127.0.0.1")
    ap.add_argument("--port", type=int, default=8900)
    ap.add_argument("--upstream-timeout", type=float,
                    default=float(os.environ.get("INFERENCE_TIMEOUT", "900")))
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    VERBOSE, UPSTREAM_TIMEOUT = a.verbose, a.upstream_timeout

    try:
        base, model, key = resolve_upstream()
    except Exception as exc:  # noqa: BLE001
        print(f"✗ cannot start gateway: {exc}", file=sys.stderr)
        return 2

    backend = os.environ.get("INFERENCE_BACKEND") or "legacy"
    print(f"▶ inference.local gateway  http://{a.host}:{a.port}/v1")
    print(f"  upstream: [{backend}] {base}  model={model}  key={_mask(key)}")
    print("  the provider credential lives HERE (host-side); the sandbox sends a dummy token")
    print(f"  operator: `echo '127.0.0.1 inference.local' | sudo tee -a /etc/hosts` so the "
          f"agent's https://inference.local/v1 resolves to this process")
    srv = build_server(a.host, a.port)
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n▪ stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
