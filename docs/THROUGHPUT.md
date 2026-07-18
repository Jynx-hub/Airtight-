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

## Reproducibility — a second, independent run agrees

The sweep above was re-run ~10 minutes later against the same warm deployment, from a
separate session, with the same harness and settings. Raw JSON:
`runtime/bench-results/sweep-20260718T060846Z.json`, captured **06:08 UTC**.

| Concurrency | Run A tok/s | Run B tok/s | Δ |
|---:|---:|---:|---:|
| 1 | 65.2 | 67.6 | +3.7% |
| 2 | 88.0 | 96.9 | +10.1% |
| 4 | 150.2 | 187.4 | +24.8% |
| 8 | 362.4 | 369.8 | +2.0% |
| **16** | **695.8** | **712.0** | **+2.3%** |
| 32 | 722.7 | 726.4 | +0.5% |

**Both runs land the same headline and the same knee**: 10.67× vs **10.53×** C=1→C=16, knee
at 16 in both, zero errors in both, exact `ignore_eos` token counts in both. The claim
reproduces; it is not one lucky sweep.

**Where the two runs disagree, and why it doesn't matter.** The mid-curve points are noisy
— C=4 differs by 25%. Those levels fire only 8 requests (`max(8, 2×concurrency)`), so a
single slow request moves the average a lot, and at low concurrency the per-level ramp-up
and drain are a large fraction of a short wall clock. The points the argument actually
rests on — C=1, C=16, C=32 — reproduce within 4%. If a level's exact value ever needs to
be load-bearing, raise the request count there rather than quoting a single run.

Run B passed the container-boundary check independently: its sweep ended **06:08:46 UTC**
and the next container began loading the model at **06:09:26**, 40s later — too late to
serve any measured request. Both runs are therefore single-A100 numbers.

## Second profile — L40S/FP8, and why the demo does not run on it

Re-measured **2026-07-18 06:57 UTC** on `l40s-fp8` (Nemotron-3-Nano-30B-A3B **FP8**,
ModelOpt quantization, `--kv-cache-dtype fp8`, 128k ctx, same harness and settings).
Raw JSON: `runtime/bench-results/sweep-20260718T065759Z.json`.

| Concurrency | A100 BF16 tok/s | L40S FP8 tok/s | Δ |
|---:|---:|---:|---:|
| 1 | 65.2 | **91.8** | +41% |
| 2 | 88.0 | **142.0** | +61% |
| 4 | 150.2 | **285.9** | +90% |
| 8 | 362.4 | **549.7** | +52% |
| **16** | 695.8 | **865.2** | **+24%** |
| 32 | 722.7 | **1008.9** | +40% |

**L40S/FP8 is faster at every level and costs less per hour** ($1.95 vs $2.50). Zero errors
at every level. On raw serving economics it is the better box, and the batching gain
reproduces on it: **9.42× C=1→C=16, 10.99× at peak.**

**Two things are weaker on L40S, and both are honest caveats rather than deal-breakers:**

- **The knee is not clean.** On A100, C=32 buys only +3.9% over C=16 — a saturated batch.
  On L40S, C=32 still adds +16.6%, so `bench.py` reports no knee at all. The cap is still
  binding — TTFT p50 jumps **4.8×** (0.453s → 2.183s) and p50 latency 1.64× for that 17%
  — but the crisp "aggregate throughput plateaus exactly at the pinned `--max-num-seqs 16`"
  story is an A100 result, not a universal one. Quote the knee claim from the A100 run.
- **The multiple is lower because the baseline is faster.** 9.42× vs 10.67× is not worse
  batching; it is a 41% faster single-stream baseline (91.8 vs 65.2 tok/s) dividing into a
  24% faster C=16. A speedup ratio rewards a slow baseline. The absolute number — 865 tok/s
  on one mid-range GPU — is the stronger claim.

### The disqualifier: cold-start recovery

| | A100 BF16 | L40S FP8 |
|---|---|---|
| vLLM `init engine` | **29.3s** | **493.5s / 601.6s** (two runs) |
| Graph capture | 14s | 42s |
| Full cold start → first token | ~1–2 min | **812.3s cold Volume / 736.8s warmed Volume** |

The L40S cold start is ~**12 minutes**, and it is *not* a caching problem — the second
measurement had warm weights *and* a warm `torch.compile` cache and still took 736.8s,
because the cost is vLLM's `profile / create kv cache / warmup model` phase on FP8 MoE
kernels (L40S is Ada/SM89, so FlashInfer falls back from TRTLLM to **CUTLASS** MoE).
Modal also had to **queue for L40S capacity** before scheduling, which the A100 never did.

During this same session Modal **preempted a running container**. On A100 that costs ~1–2
minutes; on L40S it costs ~12 minutes of dead air in front of judges. That is why
`MODAL_GPU_PROFILE` defaults to `a100-bf16` — the judged profile is chosen for recovery
time, not for price or peak throughput.

**What the two profiles jointly prove:** continuous batching delivers a ~9–11× aggregate
throughput gain across **two different GPUs, two different precisions, and two different
attention backends** (FLASH_ATTN on A100, FLASHINFER on L40S). That is a stronger claim
than any single sweep.

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

- **Both profiles are now measured** (§Second profile). The demo runs `a100-bf16`, which is
  also what the headline above was measured on — the earlier "re-run this if the demo ships
  on L40S" caveat is resolved: it was re-run, and the demo stayed on A100 anyway.
- **Cold start is profile-dependent and was previously understated.** A100 recovers in
  ~1–2 min (`init engine` 29.3s). L40S/FP8 takes **736.8–812.3s (~12 min)**, measured, with
  caches warm. Either way: deploy `MODAL_MIN_CONTAINERS=1` before judging so no cold start
  can land in the demo, then set it back to 0. Pin at **T-minus 15**, not T-minus 5.
- Idle containers scale to zero after 5 min (`scaledown_window`), so an abandoned warm box
  stops billing on its own. Observed lag from last request to `tasks=0` was ~5.9 min.
- **Preemption is real.** Modal preempted a container mid-session on 2026-07-18
  ("Container terminated due to preemption. Your Function will be restarted"). Recovery
  time therefore belongs in the profile decision, not just cost and throughput.
