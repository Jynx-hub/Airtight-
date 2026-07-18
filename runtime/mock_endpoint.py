"""Airtight runtime — an offline stand-in for the vLLM endpoint (NO GPU, NO credits).

Why this exists: the Modal deployment is metered and normally PAUSED, so debugging a
load test against it means paying a ~2-5 min cold start every time you fix a typo. This
is a local, stdlib-only server that speaks enough of the OpenAI API for `bench.py` and
`verify.sh` to be built and validated end-to-end at zero cost. Get the harness green
here, then spend exactly ONE short live window on the real endpoint.

It also doubles as the stub doorway `../docs/INFERENCE-LOCAL.md` allows, so downstream
lanes can build against a live-shaped hop before M1b lands.

What it fakes on purpose: **continuous batching**. Per-token pacing is recomputed on
every token from the CURRENT in-flight count, so aggregate throughput climbs sublinearly
with concurrency up to `--max-num-seqs` and then flattens — the same knee the real
server has at 16 (`modal_app.py` `--max-num-seqs 16` + `@modal.concurrent(max_inputs=16)`).
That makes the sweep logic and the curve math testable without a GPU. The absolute
numbers are meaningless; only the SHAPE is, and the shape is what bench.py must detect.

Run:   python runtime/mock_endpoint.py --port 8001
Drive: python runtime/bench.py --sweep --base-url http://127.0.0.1:8001/v1
"""
from __future__ import annotations

import argparse
import json
import threading
import time
import uuid
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ── Fake-GPU model ────────────────────────────────────────────────────────────
# Tuned only so the knee is unmistakable; these are not claims about real hardware.
BASE_TOK_S = 40.0        # single-stream decode rate at concurrency 1
BATCH_EXPONENT = 0.75    # sublinear batching gain: aggregate ≈ BASE * eff**0.75
CAP = 16                 # mirrors --max-num-seqs; beyond this, requests queue
MODEL = "nemotron"
API_KEY = "airtight-local"
VERBOSE = False
# Emit stream deltas as `reasoning_content` instead of `content`. This reproduces the real
# deployment's streaming behaviour with reasoning OFF: nano_v3_reasoning_parser.py only
# overrides the NON-streaming extract_reasoning, so streaming falls through to DeepSeek-R1's
# parser, which assumes output opens inside a think block and labels every token as
# reasoning. A harness that counts only `content` reads 0 tokens / NaN TTFT from a healthy
# server — so bench.py must be validated against this shape too, not just the happy one.
REASONING_CONTENT = False

_inflight = 0
_lock = threading.Lock()

_WORDS = ["hinge", "foldable", "display", "assembly", "prior", "art", "claim", "US",
          "patent", "flexible", "substrate", "actuator", "housing", "pivot"]


def _token_interval() -> float:
    """Seconds to wait before emitting the next token, given current load.

    Recomputed per token (not per request) so a request that starts while others are
    already decoding immediately shares the batch — that IS continuous batching.
    """
    with _lock:
        n = _inflight
    n = max(n, 1)
    effective = min(n, CAP)                          # past CAP the extras queue
    aggregate = BASE_TOK_S * (effective ** BATCH_EXPONENT)
    per_request = aggregate / n                      # everyone shares the aggregate
    return 1.0 / max(per_request, 0.1)


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"                    # keep-alive + chunked streaming

    # ── plumbing ──────────────────────────────────────────────────────────────
    def log_message(self, fmt: str, *args: object) -> None:
        if VERBOSE:
            super().log_message(fmt, *args)

    def _authorized(self) -> bool:
        return self.headers.get("Authorization", "") == f"Bearer {API_KEY}"

    def _send_json(self, status: int, payload: dict) -> None:
        body = json.dumps(payload).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def _chunk(self, data: bytes) -> None:
        """One HTTP chunked-transfer frame, flushed immediately (SSE needs the flush)."""
        self.wfile.write(b"%X\r\n" % len(data))
        self.wfile.write(data)
        self.wfile.write(b"\r\n")
        self.wfile.flush()

    # ── routes ────────────────────────────────────────────────────────────────
    def do_GET(self) -> None:
        if not self._authorized():
            return self._send_json(401, {"error": {"message": "invalid api key"}})
        if self.path.rstrip("/").endswith("/models"):
            return self._send_json(200, {
                "object": "list",
                "data": [{"id": MODEL, "object": "model", "owned_by": "airtight-mock"}],
            })
        self._send_json(404, {"error": {"message": f"no route {self.path}"}})

    def do_POST(self) -> None:
        if not self._authorized():
            return self._send_json(401, {"error": {"message": "invalid api key"}})
        if not self.path.rstrip("/").endswith("/chat/completions"):
            return self._send_json(404, {"error": {"message": f"no route {self.path}"}})

        length = int(self.headers.get("Content-Length", "0"))
        try:
            req = json.loads(self.rfile.read(length) or b"{}")
        except json.JSONDecodeError:
            return self._send_json(400, {"error": {"message": "bad json"}})

        n_tokens = int(req.get("max_tokens") or req.get("max_completion_tokens") or 16)
        wants_tool = bool(req.get("tools"))
        include_usage = bool((req.get("stream_options") or {}).get("include_usage"))

        global _inflight
        with _lock:
            _inflight += 1
        try:
            if req.get("stream"):
                self._stream(n_tokens, include_usage)
            else:
                self._blocking(n_tokens, wants_tool)
        finally:
            with _lock:
                _inflight -= 1

    # ── response bodies ───────────────────────────────────────────────────────
    def _blocking(self, n_tokens: int, wants_tool: bool) -> None:
        for _ in range(n_tokens):
            time.sleep(_token_interval())
        if wants_tool:
            message = {
                "role": "assistant",
                "content": None,
                "tool_calls": [{
                    "id": f"call_{uuid.uuid4().hex[:8]}",
                    "type": "function",
                    "function": {"name": "search_prior_art",
                                 "arguments": json.dumps({"query": "foldable phone hinge"})},
                }],
            }
            finish = "tool_calls"
        else:
            message = {"role": "assistant", "content": "AIRTIGHT-OK"}
            finish = "stop"
        self._send_json(200, {
            "id": f"chatcmpl-{uuid.uuid4().hex[:12]}",
            "object": "chat.completion",
            "model": MODEL,
            "choices": [{"index": 0, "message": message, "finish_reason": finish}],
            "usage": {"prompt_tokens": 32, "completion_tokens": n_tokens,
                      "total_tokens": 32 + n_tokens},
        })

    def _stream(self, n_tokens: int, include_usage: bool) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        cid = f"chatcmpl-{uuid.uuid4().hex[:12]}"

        def sse(payload: dict) -> None:
            self._chunk(b"data: " + json.dumps(payload).encode() + b"\n\n")

        def frame(delta: dict, finish: str | None) -> dict:
            return {"id": cid, "object": "chat.completion.chunk", "model": MODEL,
                    "choices": [{"index": 0, "delta": delta, "finish_reason": finish}]}

        sse(frame({"role": "assistant", "content": ""}, None))
        # Exactly n_tokens content chunks — one chunk per token, as vLLM does. This is
        # what lets bench.py assert `ignore_eos` produced a fixed-length completion.
        key = "reasoning_content" if REASONING_CONTENT else "content"
        for i in range(n_tokens):
            time.sleep(_token_interval())
            sse(frame({key: _WORDS[i % len(_WORDS)] + " "}, None))
        sse(frame({}, "stop"))
        if include_usage:
            sse({"id": cid, "object": "chat.completion.chunk", "model": MODEL, "choices": [],
                 "usage": {"prompt_tokens": 32, "completion_tokens": n_tokens,
                           "total_tokens": 32 + n_tokens}})
        self._chunk(b"data: [DONE]\n\n")
        self.wfile.write(b"0\r\n\r\n")               # end of chunked body
        self.wfile.flush()


def main() -> None:
    global BASE_TOK_S, CAP, MODEL, API_KEY, VERBOSE, REASONING_CONTENT
    ap = argparse.ArgumentParser(description="Offline OpenAI-compatible fake for bench.py")
    ap.add_argument("--port", type=int, default=8001)
    ap.add_argument("--max-num-seqs", type=int, default=CAP,
                    help="fake batch cap; the throughput curve should knee here")
    ap.add_argument("--base-tok-s", type=float, default=BASE_TOK_S)
    ap.add_argument("--model", default=MODEL)
    ap.add_argument("--api-key", default=API_KEY)
    ap.add_argument("--reasoning-content", action="store_true",
                    help="emit stream deltas as reasoning_content (the real deployment's "
                         "shape with reasoning off) — bench.py must still count these")
    ap.add_argument("--verbose", action="store_true")
    a = ap.parse_args()
    CAP, BASE_TOK_S, MODEL, API_KEY, VERBOSE = (
        a.max_num_seqs, a.base_tok_s, a.model, a.api_key, a.verbose)
    REASONING_CONTENT = a.reasoning_content

    srv = ThreadingHTTPServer(("127.0.0.1", a.port), Handler)
    srv.daemon_threads = True
    print(f"▶ mock inference endpoint  http://127.0.0.1:{a.port}/v1  model={MODEL}")
    print(f"  fake GPU: {BASE_TOK_S:.0f} tok/s single-stream, batch cap {CAP} "
          f"(expect the throughput knee at concurrency {CAP})")
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\n▪ stopped")


if __name__ == "__main__":
    main()
