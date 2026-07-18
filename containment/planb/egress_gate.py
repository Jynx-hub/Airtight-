"""§8 Plan B — the real egress gate. THE socket-level 403 the [SIM] demo could only print.

Every outbound request the sandbox makes is an HTTP forward-proxy request to this
process (the sandbox has HTTP(S)_PROXY set to here, and — because it lives on a
docker `internal` network — has no other route off-box at all). The gate runs the
SAME `containment.policy.decide()` the offline demo uses and:

  ALLOW               -> forwards to the upstream and returns its real response
  HARD_DENY           -> real HTTP 403, reason: irreversible, not escalable
  DEFAULT_DENY_ESCALATE -> real HTTP 403 carrying the Policy Advisor guidance +
                          a proposal id the sandbox can escalate on

This is the network/inference tier of the four-tier model, enforced for real on
Linux (Landlock/seccomp isolation is applied to the *sandbox* container; this gate
is the host-side policy decision point). Nothing here is a print(): a denied egress
gets a 403 status line over a real socket, and the sandbox has no way around it.
"""
from __future__ import annotations

import json
import os
import sys
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlsplit

sys.path.insert(0, "/app")  # the repo is mounted here in the container
from containment.policy import Decision, decide  # noqa: E402

POLICY = os.environ.get("POLICY", "/app/inference/policy/airtight-sandbox.yaml")
UPSTREAM = os.environ.get("UPSTREAM", "http://upstream:8080")  # where ALLOWed egress goes
# A5: the audit->enforce sweep, for real. `audit` logs every decision and lets traffic
# THROUGH (observe the real egress set); `enforce` returns the real 403. Same gate, one env.
ENFORCE = os.environ.get("ENFORCE", "enforce").strip().lower()
_n = [0]


def _log(mode: str, decision: str, method: str, host: str, path: str):
    print(f"[gate:{mode}] {decision:<21} {method:<4} {host}{path}", flush=True)


class Gate(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    def log_message(self, *a):  # quiet
        pass

    def _send(self, status: int, payload: dict, extra_headers: dict | None = None):
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra_headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _decide_and_route(self, method: str, raw: bytes | None):
        # Forward-proxy requests carry an absolute URI in the request line.
        u = urlsplit(self.path)
        host, path = (u.hostname or ""), (u.path or "/")
        # A2: in enforce mode honor each endpoint's `enforcement:` field from the YAML
        # (override=None); in audit mode force global observe. Deny_rules (hard-deny) are
        # mode-independent either way.
        result = decide("egress", host, method, path, policy_path=POLICY,
                        enforcement_override=(None if ENFORCE == "enforce" else "audit"))
        _log(ENFORCE, result.decision.value, method, host, path)

        # A5 audit mode: observe the real egress set, let it through (research §5).
        if ENFORCE == "audit" and result.decision is not Decision.ALLOW:
            return self._forward_allow(method, path, raw, mode="audit")

        if result.decision is Decision.HARD_DENY:
            return self._send(403, {
                "gate": "openshell-planb", "decision": "hard_deny",
                "host": host, "method": method, "path": path,
                "error": {"code": 403, "message": "egress denied by policy (irreversible, not escalable)"},
                "reason": result.reason, "matched_rule": result.matched_rule,
            }, {"X-Airtight-Decision": "hard_deny"})

        if result.decision is Decision.DEFAULT_DENY_ESCALATE:
            _n[0] += 1
            return self._send(403, {
                "gate": "openshell-planb", "decision": "default_deny_escalate",
                "host": host, "method": method, "path": path,
                "error": {"code": 403, "message": "egress default-denied; submit a Policy Advisor proposal"},
                "agent_guidance": result.agent_guidance,
                "proposal_hint": {"chunk_id": f"prop-{_n[0]:04d}", "op": "addRule",
                                  "rule": {"host": host, "method": method, "path": path}},
            }, {"X-Airtight-Decision": "default_deny_escalate"})

        # ALLOW: forward to the upstream (demo forwards all allowed egress to the stub;
        # in production the gate forwards to the real host in the URL).
        return self._forward_allow(method, path, raw, mode="allow")

    def _forward_allow(self, method: str, path: str, raw: bytes | None, mode: str):
        target = f"{UPSTREAM}{path}"
        req = urllib.request.Request(target, data=raw, method=method,
                                     headers={"Content-Type": "application/json"})
        try:
            resp = urllib.request.urlopen(req, timeout=10)
            data = resp.read()
            self.send_response(resp.status)
            self.send_header("Content-Type", resp.headers.get("Content-Type", "application/json"))
            self.send_header("Content-Length", str(len(data)))
            self.send_header("X-Airtight-Decision", mode)  # "allow" or "audit" (observed, not blocked)
            self.end_headers()
            self.wfile.write(data)
        except urllib.error.URLError as exc:
            self._send(502, {"error": {"message": f"gate upstream error: {exc}"}})

    def do_GET(self):
        self._decide_and_route("GET", None)

    def do_POST(self):
        length = int(self.headers.get("Content-Length", "0"))
        self._decide_and_route("POST", self.rfile.read(length) if length else b"")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", "8888"))
    print(f"[gate] openshell-planb egress gate on :{port}  mode={ENFORCE}  policy={POLICY}",
          flush=True)
    ThreadingHTTPServer(("0.0.0.0", port), Gate).serve_forever()
