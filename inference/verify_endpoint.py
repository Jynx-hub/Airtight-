"""Verify an OpenAI-compatible endpoint and capture throughput numbers (F2).

Works unchanged against the dev vLLM URL, the NIM cloud fallback, and the
in-sandbox inference.local route — the base URL is opaque:

    python inference/verify_endpoint.py --base-url https://<workspace>--airtight-vllm-serve.modal.run/v1
    python inference/verify_endpoint.py --base-url ... --concurrency 16 --requests 32

The concurrency run doubles as the vLLM-bounty evidence (continuous batching
under concurrent load) — save the printed numbers.
"""

import argparse
import statistics
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from openai import OpenAI

PROMPT = "In one sentence, what is a patent claim?"


def one_request(client: OpenAI, model: str) -> float:
    t0 = time.perf_counter()
    client.chat.completions.create(
        model=model,
        messages=[{"role": "user", "content": PROMPT}],
        max_tokens=64,
    )
    return time.perf_counter() - t0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", required=True)
    ap.add_argument("--api-key", default="dummy")
    ap.add_argument("--model", default=None, help="defaults to the first served model")
    ap.add_argument("--concurrency", type=int, default=8)
    ap.add_argument("--requests", type=int, default=16)
    args = ap.parse_args()

    client = OpenAI(base_url=args.base_url, api_key=args.api_key)

    print(f"== {args.base_url}")
    models = [m.id for m in client.models.list()]
    print(f"served models: {models}")
    model = args.model or models[0]
    print(f"using model:   {model}\n")

    print("chat completion ...", end=" ", flush=True)
    dt = one_request(client, model)
    print(f"ok ({dt:.2f}s)")

    print("streaming ..........", end=" ", flush=True)
    chunks = 0
    for event in client.chat.completions.create(
        model=model, messages=[{"role": "user", "content": PROMPT}], max_tokens=64, stream=True
    ):
        if event.choices and event.choices[0].delta.content:
            chunks += 1
    print(f"ok ({chunks} chunks)")

    n, c = args.requests, args.concurrency
    print(f"\nconcurrent load: {n} requests at concurrency {c} ...")
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=c) as pool:
        latencies = list(pool.map(lambda _: one_request(client, model), range(n)))
    wall = time.perf_counter() - t0

    print(f"  wall clock      {wall:.2f}s")
    print(f"  throughput      {n / wall:.2f} req/s")
    print(f"  latency p50     {statistics.median(latencies):.2f}s")
    print(f"  latency max     {max(latencies):.2f}s")
    print("\nSave these numbers — they are the vLLM-bounty evidence.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
