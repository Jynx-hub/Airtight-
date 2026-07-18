"""Airtight runtime — concurrent-batching throughput harness (F2 / $500 vLLM bounty).

What this measures and why: the bounty's first criterion is **efficiency under concurrent
load**, and the recursive engine's real workload is a heartbeat fanning out concurrent
prior-art retrieval sub-agents. That is precisely vLLM's continuous-batching case. This
sweeps concurrency and records what the server actually does with it.

The headline number is the C=1 → C=16 aggregate-throughput multiple: the same work fired
one-at-a-time versus batched. `modal_app.py` pins `--max-num-seqs 16` and
`@modal.concurrent(max_inputs=16)`, so the curve should climb to 16 and then flatten as
requests queue. Sweeping past 16 is what proves 16 is the real ceiling and not just where
we stopped looking.

Methodology notes that matter for the writeup:
  * Every request STREAMS, so time-to-first-token falls out of the same run that proves
    F2's "chat + streaming" clause. One harness, two deliverables.
  * `ignore_eos` + fixed `max_tokens` forces every request to emit exactly the same number
    of output tokens. Without it, variable completion lengths make tok/s incomparable
    across levels and the whole comparison is mush.
  * Greedy decoding (temperature 0) — standard benchmark setting, removes sampling noise.
  * Each level's wall clock includes its own ramp-up and drain, which slightly UNDERSTATES
    throughput at high concurrency. We accept that: it biases against our own headline.

On the design invariant: this bypasses `inference_local.py` because it is operator
measurement tooling, not agent traffic — it measures the server, not the doorway. It still
reads the same operator-pinned INFERENCE_* env, so it cannot be aimed anywhere the operator
did not choose. `--base-url` exists only to point at `mock_endpoint.py` for offline
validation. The doorway itself is verified separately (`python runtime/inference_local.py`).

Offline (free, no GPU — do this first):
    python runtime/mock_endpoint.py --port 8001 &
    python runtime/bench.py --sweep --base-url http://127.0.0.1:8001/v1

Live (metered — only inside a deliberate window):
    python runtime/bench.py --warmup --gpu "A100-80GB / Nano BF16"
    python runtime/bench.py --sweep  --gpu "A100-80GB / Nano BF16"
"""
from __future__ import annotations

import argparse
import asyncio
import json
import math
import os
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from openai import AsyncOpenAI

try:
    from dotenv import load_dotenv

    load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))
except ImportError:
    pass

RESULTS_DIR = Path(__file__).parent / "bench-results"
DEFAULT_LEVELS = [1, 2, 4, 8, 16, 32]
DEFAULT_MAX_TOKENS = 128

# The workload is shaped like a retrieval sub-agent turn, not generic chat — same shape as
# verify.sh's tool-call probe, so the number describes the traffic the heartbeat actually
# generates. Reasoning stays OFF (deterministic tool-call turns, per the doorway contract).
PROMPT = (
    "You are a prior-art retrieval sub-agent. Summarize the closest prior art for a "
    "foldable phone hinge with a flexible display substrate. Be specific and concise."
)


# ── results model ─────────────────────────────────────────────────────────────
@dataclass
class Endpoint:
    """Operator-pinned target. Carried around so each level can build a fresh client."""
    base_url: str
    model: str
    api_key: str
    timeout: float

    def client(self) -> AsyncOpenAI:
        # max_retries=0: during a metered window we want to SEE failures, not silently pay
        # for retries that hide a broken endpoint or quietly inflate a latency sample.
        return AsyncOpenAI(base_url=self.base_url, api_key=self.api_key,
                           timeout=self.timeout, max_retries=0)


@dataclass
class RequestResult:
    ok: bool
    latency_s: float = 0.0
    ttft_s: float = float("nan")
    output_tokens: int = 0
    chunk_tokens: int = 0          # counted from stream chunks, cross-checks `usage`
    error: str = ""


@dataclass
class LevelResult:
    concurrency: int
    requests: int
    wall_s: float
    output_tokens: int
    aggregate_tok_s: float
    requests_s: float
    latency_p50: float
    latency_p95: float
    ttft_p50: float
    ttft_p95: float
    errors: int
    error_samples: list[str] = field(default_factory=list)
    token_count_mismatch: bool = False


def _pct(xs: list[float], p: float) -> float:
    """Nearest-rank percentile. Small-n friendly; no interpolation games."""
    vals = sorted(v for v in xs if not math.isnan(v))
    if not vals:
        return float("nan")
    k = max(0, min(len(vals) - 1, math.ceil(p / 100 * len(vals)) - 1))
    return vals[k]


# ── one request ───────────────────────────────────────────────────────────────
async def _one_request(client: AsyncOpenAI, model: str, max_tokens: int) -> RequestResult:
    started = time.perf_counter()
    ttft = float("nan")
    chunk_tokens = 0
    usage_tokens = 0
    try:
        stream = await client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": PROMPT}],
            max_tokens=max_tokens,
            temperature=0.0,
            stream=True,
            stream_options={"include_usage": True},
            extra_body={
                # vLLM: emit exactly max_tokens so every request is the same size of work.
                "ignore_eos": True,
                "chat_template_kwargs": {"enable_thinking": False},
            },
        )
        async for chunk in stream:
            if getattr(chunk, "usage", None):
                usage_tokens = chunk.usage.completion_tokens or 0
            if not chunk.choices:
                continue
            delta = chunk.choices[0].delta
            # Count content OR reasoning_content. Both are decoded tokens and cost the
            # server identically, so either one starts the TTFT clock. The `or` is not
            # defensive padding — on this deployment reasoning-off output arrives
            # ENTIRELY as `reasoning_content` when streaming: nano_v3_reasoning_parser.py
            # only overrides the non-streaming `extract_reasoning`, so the streaming path
            # falls through to DeepSeek-R1's, which assumes output opens inside a think
            # block and mislabels every token. Counting `content` alone reads 0 tokens and
            # a NaN TTFT against a server that is in fact generating fine.
            if getattr(delta, "content", None) or getattr(delta, "reasoning_content", None):
                if math.isnan(ttft):
                    ttft = time.perf_counter() - started   # first real token, not the role frame
                chunk_tokens += 1
    except Exception as exc:                                # noqa: BLE001 — record, never mask
        return RequestResult(ok=False, latency_s=time.perf_counter() - started,
                             error=f"{type(exc).__name__}: {exc}"[:200])

    return RequestResult(
        ok=True,
        latency_s=time.perf_counter() - started,
        ttft_s=ttft,
        output_tokens=usage_tokens or chunk_tokens,
        chunk_tokens=chunk_tokens,
    )


# ── one concurrency level ─────────────────────────────────────────────────────
async def _run_level(ep: Endpoint, concurrency: int,
                     n_requests: int, max_tokens: int) -> LevelResult:
    # A FRESH client (and so a fresh connection pool) per level. Connections pooled across
    # the inter-level settle go stale — the server drops the idle socket, the client then
    # writes a request into a half-closed one and the whole level dies with
    # RemoteProtocolError. Observed offline at C=32 after earlier levels; half the requests
    # were lost. Within a level, connections stay hot and get reused normally, so this
    # costs nothing measurable and avoids masking real failures with retries.
    client = ep.client()
    gate = asyncio.Semaphore(concurrency)

    async def guarded() -> RequestResult:
        async with gate:                                    # keeps exactly `concurrency` in flight
            return await _one_request(client, ep.model, max_tokens)

    started = time.perf_counter()
    try:
        results = await asyncio.gather(*(guarded() for _ in range(n_requests)))
        wall = time.perf_counter() - started
    finally:
        await client.close()

    ok = [r for r in results if r.ok]
    bad = [r for r in results if not r.ok]
    total_tokens = sum(r.output_tokens for r in ok)

    return LevelResult(
        concurrency=concurrency,
        requests=n_requests,
        wall_s=round(wall, 3),
        output_tokens=total_tokens,
        aggregate_tok_s=round(total_tokens / wall, 1) if wall > 0 else 0.0,
        requests_s=round(len(ok) / wall, 3) if wall > 0 else 0.0,
        latency_p50=round(_pct([r.latency_s for r in ok], 50), 3),
        latency_p95=round(_pct([r.latency_s for r in ok], 95), 3),
        ttft_p50=round(_pct([r.ttft_s for r in ok], 50), 3),
        ttft_p95=round(_pct([r.ttft_s for r in ok], 95), 3),
        errors=len(bad),
        error_samples=[r.error for r in bad[:3]],
        # If `usage` and the chunk count disagree, one token != one chunk on this server
        # and the tok/s figures need a caveat in the writeup.
        token_count_mismatch=any(r.chunk_tokens != r.output_tokens for r in ok),
    )


# ── provenance ────────────────────────────────────────────────────────────────
async def _provenance(ep: Endpoint, gpu: str, notes: str) -> dict[str, Any]:
    """Best-effort: never let metadata collection break a metered run."""
    prov: dict[str, Any] = {
        "captured_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "base_url": ep.base_url,
        "served_model": ep.model,
        # The client cannot see the GPU. `.env` is NOT authoritative — modal-deploy.sh and a
        # bare `modal deploy` resolve different profiles. Read the real one from Modal's App
        # Logs (`▶ Serving {checkpoint} on {gpu}`) and pass it via --gpu.
        "gpu_reported_by_operator": gpu or "UNSPECIFIED — read Modal App Logs and re-run with --gpu",
        "notes": notes,
        "max_num_seqs_deployed": 16,
        "modal_concurrent_max_inputs": 16,
    }
    client = ep.client()
    try:
        models = await client.models.list()
        prov["models_endpoint"] = [m.id for m in models.data]
    except Exception as exc:                                # noqa: BLE001
        prov["models_endpoint_error"] = str(exc)[:200]
    finally:
        await client.close()
    return prov


# ── reporting ─────────────────────────────────────────────────────────────────
def _markdown(levels: list[LevelResult]) -> str:
    head = ("| Concurrency | Reqs | Wall (s) | Out tok | **Aggregate tok/s** | Req/s | "
            "Lat p50 | Lat p95 | TTFT p50 | TTFT p95 | Err |")
    sep = "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|"
    rows = [
        f"| {l.concurrency} | {l.requests} | {l.wall_s} | {l.output_tokens} | "
        f"**{l.aggregate_tok_s}** | {l.requests_s} | {l.latency_p50} | {l.latency_p95} | "
        f"{l.ttft_p50} | {l.ttft_p95} | {l.errors} |"
        for l in levels
    ]
    return "\n".join([head, sep, *rows])


def _knee(levels: list[LevelResult], gain_threshold: float = 0.10) -> int | None:
    """Lowest concurrency past which the next level buys < `gain_threshold` more throughput.

    This is the number that proves 16 is a real ceiling and not just where we stopped
    sweeping — the curve flattens there because `--max-num-seqs 16` is the batch cap.
    """
    for cur, nxt in zip(levels, levels[1:]):
        if cur.aggregate_tok_s <= 0:
            continue
        if (nxt.aggregate_tok_s - cur.aggregate_tok_s) / cur.aggregate_tok_s < gain_threshold:
            return cur.concurrency
    return None


def _summary(levels: list[LevelResult], operating_point: int = 16) -> dict[str, Any]:
    ok = [l for l in levels if l.aggregate_tok_s > 0]
    if not ok:
        return {"verdict": "NO DATA — every level failed"}
    baseline = next((l for l in ok if l.concurrency == 1), ok[0])
    peak = max(ok, key=lambda l: l.aggregate_tok_s)
    base_tps = baseline.aggregate_tok_s or 1.0

    out: dict[str, Any] = {
        "baseline_concurrency": baseline.concurrency,
        "baseline_tok_s": baseline.aggregate_tok_s,
        "peak_concurrency": peak.concurrency,
        "peak_tok_s": peak.aggregate_tok_s,
        "peak_speedup_x": round(peak.aggregate_tok_s / base_tps, 2),
        "knee_concurrency": _knee(levels),
    }
    # The HEADLINE is the deployed operating point (--max-num-seqs), not the peak. Past the
    # cap, extra concurrency only queues: throughput barely moves while latency inflates, so
    # quoting the peak would flatter the result by measuring the wrong thing.
    op = next((l for l in ok if l.concurrency == operating_point), None)
    if op:
        out |= {
            "operating_point_concurrency": op.concurrency,
            "operating_point_tok_s": op.aggregate_tok_s,
            "headline_speedup_x": round(op.aggregate_tok_s / base_tps, 2),
            "latency_cost_p50_x": (round(op.latency_p50 / baseline.latency_p50, 2)
                                   if baseline.latency_p50 else None),
        }
    headline = out.get("headline_speedup_x", out["peak_speedup_x"])
    # Sanity gate: if batching isn't engaging, this is not bounty evidence.
    out["verdict"] = ("batching engaged" if headline >= 2
                      else "SUSPECT — little/no batching gain; investigate before publishing")
    return out


# ── modes ─────────────────────────────────────────────────────────────────────
async def do_warmup(ep: Endpoint) -> None:
    """First request after an un-pause. Its latency IS the cold-start number F4 needs."""
    print("▶ warmup — first request after cold start "
          "(~1-2 min on a100-bf16, ~12 min on l40s-fp8)")
    client = ep.client()
    started = time.perf_counter()
    try:
        r = await _one_request(client, ep.model, max_tokens=16)
    finally:
        await client.close()
    elapsed = time.perf_counter() - started
    if not r.ok:
        print(f"✖ warmup FAILED after {elapsed:.1f}s — {r.error}")
        raise SystemExit(1)
    print(f"✔ endpoint awake — cold start + first inference: {elapsed:.1f}s "
          f"(TTFT {r.ttft_s:.1f}s, {r.output_tokens} tok)")
    print("  ↳ record this in docs/THROUGHPUT.md and the F4 keep-warm runbook")


async def do_sweep(ep: Endpoint, levels: list[int], max_tokens: int,
                   gpu: str, notes: str, out_dir: Path) -> None:
    prov = await _provenance(ep, gpu, notes)
    print(f"▶ sweep {levels}  max_tokens={max_tokens} (ignore_eos)  model={ep.model}")
    print(f"  {ep.base_url}\n")

    results: list[LevelResult] = []
    for c in levels:
        n = max(8, 2 * c)
        print(f"  · C={c:<3} firing {n} requests …", end="", flush=True)
        lvl = await _run_level(ep, c, n, max_tokens)
        results.append(lvl)
        flag = f"  ⚠ {lvl.errors} errors" if lvl.errors else ""
        print(f" {lvl.aggregate_tok_s:>8.1f} tok/s   {lvl.wall_s:>6.1f}s{flag}")
        if lvl.errors:
            for e in lvl.error_samples:
                print(f"      ↳ {e}")
        # Short settle so the previous level fully drains. Deliberately kept to seconds:
        # a gap >5 min would let Modal scale to zero mid-sweep and poison the next level.
        await asyncio.sleep(2)

    summary = _summary(results)
    table = _markdown(results)
    print(f"\n{table}\n")
    if "operating_point_tok_s" in summary:
        print(f"▶ HEADLINE  {summary['baseline_tok_s']} tok/s at C=1 → "
              f"{summary['operating_point_tok_s']} tok/s at C={summary['operating_point_concurrency']} "
              f"= {summary['headline_speedup_x']}× from continuous batching "
              f"(per-request latency cost: {summary['latency_cost_p50_x']}×)")
    print(f"  peak {summary['peak_tok_s']} tok/s at C={summary['peak_concurrency']} "
          f"({summary['peak_speedup_x']}×)  ·  knee at C={summary['knee_concurrency']}")
    print(f"  verdict: {summary['verdict']}")
    if any(l.token_count_mismatch for l in results):
        print("  ⚠ usage vs chunk token counts disagree — caveat the tok/s figures")

    out_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    path = out_dir / f"sweep-{stamp}.json"
    path.write_text(json.dumps({
        "provenance": prov,
        "config": {"levels": levels, "max_tokens": max_tokens, "ignore_eos": True,
                   "temperature": 0.0, "streaming": True, "prompt": PROMPT,
                   "requests_per_level": "max(8, 2*concurrency)"},
        "levels": [asdict(l) for l in results],
        "summary": summary,
        "markdown_table": table,
    }, indent=2))
    print(f"\n✔ raw results → {path}")


def main() -> None:
    ap = argparse.ArgumentParser(description="vLLM continuous-batching throughput sweep (F2)")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--warmup", action="store_true",
                      help="single request; its latency is the cold-start number")
    mode.add_argument("--sweep", action="store_true", help="full concurrency sweep")
    ap.add_argument("--base-url", default=None,
                    help="OFFLINE VALIDATION ONLY — point at mock_endpoint.py. "
                         "Omit for the operator-pinned INFERENCE_BASE_URL.")
    ap.add_argument("--levels", default=",".join(map(str, DEFAULT_LEVELS)))
    ap.add_argument("--max-tokens", type=int, default=DEFAULT_MAX_TOKENS)
    ap.add_argument("--gpu", default="", help="GPU + checkpoint, read from Modal App Logs")
    ap.add_argument("--notes", default="")
    ap.add_argument("--timeout", type=float, default=900.0,
                    help="per-request timeout; generous so a cold start doesn't abort")
    ap.add_argument("--out-dir", default=str(RESULTS_DIR))
    a = ap.parse_args()

    ep = Endpoint(
        base_url=a.base_url or os.environ.get("INFERENCE_BASE_URL", "http://localhost:8000/v1"),
        model=os.environ.get("INFERENCE_MODEL", "nemotron"),
        api_key=os.environ.get("INFERENCE_API_KEY", "airtight-local"),
        timeout=a.timeout,
    )

    # Only the self-hosted vLLM path earns the $500 bounty; docs/COSTS.md marks the hosted
    # NIM fallback "❌ no — hosted API". Measuring it by accident and filing the number as
    # bounty evidence would be worse than having no number, so say so loudly.
    backend = os.environ.get("INFERENCE_BACKEND", "").strip().lower()
    if backend and backend != "modal" and not a.base_url:
        print(f"⚠ INFERENCE_BACKEND={backend!r} is not the self-hosted vLLM path — "
              f"these numbers do NOT count toward the vLLM bounty.\n")

    if a.warmup:
        asyncio.run(do_warmup(ep))
    else:
        levels = [int(x) for x in a.levels.split(",") if x.strip()]
        asyncio.run(do_sweep(ep, levels, a.max_tokens, a.gpu, a.notes, Path(a.out_dir)))


if __name__ == "__main__":
    main()
