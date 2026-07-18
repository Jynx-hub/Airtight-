# Airtight — Inference Throughput (F2 / $500 vLLM bounty evidence)

**Headline: 65.2 → 695.8 tokens/sec, a 10.67× throughput gain from vLLM's continuous
batching on the same GPU, same model, same prompt.** The curve knees at concurrency 16 —
exactly where `modal_app.py` pins `--max-num-seqs 16` — which is what makes the number
evidence rather than a benchmark that happened to look good.

Captured **2026-07-18 05:58 UTC**. Raw JSON: `runtime/bench-results/sweep-20260718T055914Z.json`.
Harness: `runtime/bench.py`.

## What "throughput" means here

Two different numbers get called speed, and the bounty is about the second one:

- **Per-request speed** — how fast one answer streams back. Nemotron does ~65 tok/s
  single-stream. More GPU doesn't move this much; it's mostly fixed by the model.
- **Aggregate throughput** — total tokens/sec the server produces across *everyone using
  it at once*. This is what continuous batching multiplies. vLLM's scheduler packs many
  in-flight requests into one GPU pass, so 16 concurrent users cost far less than 16× one
  user.

Airtight's real workload is the recursive heartbeat fanning out concurrent prior-art
retrieval sub-agents — many simultaneous requests, which is precisely the batching case.

## Results — A100-80GB, Nemotron-3-Nano-30B-A3B BF16, vLLM 0.12.0

| Concurrency | Reqs | Wall (s) | Out tok | **Aggregate tok/s** | Req/s | Lat p50 | Lat p95 | TTFT p50 | TTFT p95 | Err |
|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|
| 1 | 8 | 15.707 | 1024 | **65.2** | 0.509 | 1.959 | 2.092 | 0.876 | 0.957 | 0 |
| 2 | 8 | 11.642 | 1024 | **88.0** | 0.687 | 2.83 | 3.136 | 0.965 | 1.843 | 0 |
| 4 | 8 | 6.817 | 1024 | **150.2** | 1.173 | 2.81 | 4.006 | 1.507 | 2.689 | 0 |
| 8 | 16 | 5.651 | 2048 | **362.4** | 2.831 | 2.801 | 2.867 | 1.467 | 1.546 | 0 |
| 16 | 32 | 5.887 | 4096 | **695.8** | 5.436 | 2.924 | 3.004 | 1.437 | 1.482 | 0 |
| 32 | 64 | 11.336 | 8192 | **722.7** | 5.646 | 5.474 | 5.851 | 3.977 | 4.273 | 0 |

Zero failed requests at every level. Stream chunk counts matched server-reported `usage`
completion tokens exactly, so the tok/s figures need no caveat.

## Reading the curve

**The knee is the proof.** Throughput climbs steeply to C=16 (695.8 tok/s), then C=32 adds
only 3.9% more (722.7) while p50 latency nearly doubles (2.92s → 5.47s) and TTFT jumps
2.8× (1.44s → 3.98s). That is the textbook signature of a saturated batch: past the cap,
requests queue instead of batching, so you pay latency for no throughput. The cap we
measured is the cap we configured — `--max-num-seqs 16`. Sweeping past 16 is what proves
16 is the real ceiling and not just where we stopped looking.

**Latency stays nearly flat while throughput grows 10×.** From C=1 to C=16, aggregate
throughput rises 10.67× while p50 latency rises only 1.49× (1.96s → 2.92s). That is the
whole argument for self-hosted vLLM over one-request-at-a-time serving: an order of
magnitude more work per second for roughly half again the wait.

**C=16 is the operating point.** Peak raw throughput is at C=32, but it's a worse place to
run — 3.9% more tokens/sec for double the latency. Cap the heartbeat's concurrent
sub-agent fan-out at 16.

## Method (and why each choice matters)

- **`ignore_eos` + fixed `max_tokens=128`** — every request emits exactly the same number
  of output tokens. Without it, variable completion lengths make tok/s incomparable across
  levels and a server that answered tersely would look fast.
- **Streaming, with TTFT measured separately** — TTFT is queueing + prefill; the rest is
  decode. Batching trades a little TTFT for a lot of aggregate throughput, and both belong
  in the record. This also satisfies F2's "chat + streaming" clause in the same run.
- **Greedy decoding (temperature 0)** — removes sampling noise.
- **One wall clock per level**, first request out to last request done. Summing per-request
  rates would double-count concurrency.
- **Each level's clock includes its own ramp-up and drain**, which slightly *understates*
  throughput at high concurrency. Accepted deliberately: it biases against our own headline.
- **Warmup request first** — absorbs cold start and CUDA-graph capture so they never land
  inside a measured level.

### One trap to watch on a re-run: the C=32 level can cross a container boundary

`@modal.concurrent(max_inputs=16)` means each container accepts 16 concurrent inputs, so
firing 32 at once makes Modal's autoscaler start a **second container**. If that container
comes up in time to serve part of the load, the C=32 row is two A100s, not one, and the
single-GPU story silently breaks.

**It did not happen in this run — verified, not assumed.** The sweep finished at 05:59:14
UTC; the second container began loading the model at 05:59:50, 36s later. It arrived too
late to serve any measured request, so every number above came from one container and the
C=32 latency rise is genuine queueing behind the batch cap.

Check this every time before publishing a sweep: `modal app logs <app-id> | grep "Starting
to load model"` and confirm no container start falls inside the sweep window. If one does,
discard C=32 and report C=1→C=16 only.

## Reproducing

```bash
# 1. Free — validate the harness against the fake endpoint, no GPU, no credits
python runtime/mock_endpoint.py --port 8001 &
python runtime/bench.py --sweep --base-url http://127.0.0.1:8001/v1 --max-tokens 16

# 2. Metered — one deliberate live window
python runtime/bench.py --warmup
python runtime/bench.py --sweep --gpu "A100-80GB / Nemotron-3-Nano-30B-A3B BF16"
```

Requires `openai` + `python-dotenv` (`runtime/.venv`). The bench reads the same
operator-pinned `INFERENCE_*` env as the doorway, so it cannot be aimed at an endpoint the
operator did not choose; `--base-url` exists only to reach the offline mock.

## Open issue found during this run — streaming mislabels every token as reasoning

`runtime/nano_v3_reasoning_parser.py` overrides only `extract_reasoning`, the
**non-streaming** path. The streaming path falls through to vLLM's DeepSeek-R1 parser,
which assumes generation opens inside a think block. Result, with reasoning **off**:

| Mode | `content` | `reasoning_content` |
|---|---|---|
| non-streaming | the answer ✅ | empty |
| streaming | **empty** ❌ | the answer |

Verified directly — the same prompt returns `"One well‑known patent “loophole”…"` in
`content` when non-streaming and in `reasoning_content` when streaming.

Reasoning itself is genuinely off (`chat_template_kwargs: {"enable_thinking": false}`
works; omitting it, or `{"thinking": false}`, leaves reasoning on). This is purely a
**delta-routing** bug in the streaming path.

**Who this bites:** anything that streams and reads `delta.content` gets an empty string
against a server that is generating fine — Lane C's streaming UI most directly.
`bench.py` counts `content or reasoning_content` and is unaffected. Non-streaming callers,
including the doorway's current `chat()`, are unaffected.

**Fix options:** override the streaming method in the plugin too, or check whether a newer
vLLM ships `nano_v3` built-in and drop the plugin (`USE_REASONING_PLUGIN=False` in
`modal_app.py`). Not blocking F2.

## Notes for the writeup

- The deployment measured was the **A100-80GB BF16** profile (`MODAL_GPU_PROFILE=a100-bf16`
  in `runtime/.env`), not the `l40s-fp8` default documented as the cheap path. Re-run this
  sweep if the demo ships on L40S/FP8 — the numbers will differ.
- Cold start (container scaled to zero → first token) runs ~2–5 min: weights load ~36s,
  model load ~60s, then torch.compile and CUDA-graph capture. For judging, deploy with
  `MODAL_MIN_CONTAINERS=1` so no cold start lands in the demo, then set it back to 0.
- Idle containers scale to zero after 5 min (`scaledown_window`), so an abandoned warm box
  stops billing on its own.
