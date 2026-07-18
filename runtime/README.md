# Airtight Runtime (Lane A) — Nemotron on vLLM via Modal (free tier)

This is where the robot's brain lives. It stands up **Nemotron** on **Modal's free tier**,
served by **vLLM** as one OpenAI-compatible endpoint on `:8000`. That endpoint *is*
`inference.local` — the single, operator-pinned model hop that HiddenLayer (Lane B) and
OpenShell both enforce on. **One boundary, three tracks.** Nothing in Airtight
talks to the model except through this hop.

The **guaranteed path is Nemotron 3 Nano on one GPU** (fits VRAM; Modal scale-to-zero
keeps it effectively free); bring up **Super** only if you land a bigger box. Modal is
still **self-hosted vLLM**, so the **$500 vLLM bounty is intact** — it just replaces the
retired Brev plan. Read `../docs/INFERENCE-LOCAL.md` (the contract) and `../research/vllm.md`
(serving/VRAM) first; this delivers milestone **M1b**.

> Grounded in live research on 2026-07-17 (`../research/` + Modal/vLLM/NIM docs). The
> deploy step needs *your* free Modal account, a gated-weights HF token, and the current
> vLLM Nemotron 3 recipe — it hasn't been run from here. A few things are flagged to
> verify at deploy time in `../docs/COSTS.md`.

---

## Files

| File | Runs on | What it does |
|------|---------|--------------|
| `RUNBOOK.md` | — | **Start here if you only need to call the model** — consumer quickstart + the demo-day operator card |
| `.env.example` | — | Copy to `.env`; the operator-pinned config the whole system reads |
| `modal_app.py` | Modal (cloud) | **Primary** — the vLLM/Nemotron server + web endpoint (scale-to-zero) |
| `modal-deploy.sh` | your laptop | `modal deploy` the app; prints the endpoint URL |
| `serve-vllm.sh` | any GPU box | The host-agnostic `vllm serve` command (same flags `modal_app.py` runs) |
| `serve-nim.sh` | — | **Fallback** — proves the one-var NIM flip end-to-end (never writes `.env`) |
| `nano_v3_reasoning_parser.py` | Modal image | vLLM reasoning-parser plugin — the real one from the NVIDIA HF repo, loaded and working in the deployed server. **Known bug:** it overrides only the non-streaming path, so *streaming* output arrives as `reasoning_content` instead of `content` (`../docs/THROUGHPUT.md` §Open issue) |
| `verify.sh` | anywhere reaching the endpoint | Smoke-test: models list + chat + tool-call |
| `inference_local.py` | the app | The **one doorway** — every model call goes through `chat()`; `INFERENCE_BACKEND=gateway` points it at the gateway below |
| `inference_gateway.py` | host side | **A4** — the `inference.local` gateway: holds the provider key, injects it host-side, pins the model. `INFERENCE_BACKEND=modal\|nim` picks its upstream |
| `gateway_smoke.py` | your laptop | Offline 3-process proof of A4 (no GPU): dummy token rejected direct → provider (401), accepted via gateway (200), key absent from the agent env |
| `bench.py` | anywhere reaching the endpoint | **Throughput harness** — concurrency sweep, streaming + TTFT, writes `bench-results/*.json` (the $500 bounty evidence) |
| `mock_endpoint.py` | your laptop | Offline OpenAI-compatible fake with simulated batching — **validate `bench.py` here for free before spending GPU credits** |

---

## 0. Prerequisites (one-time)

- **Modal** — `pip install modal && modal token new` (free account, no card).
- **Gated weights** — the Nemotron checkpoints are gated under the NVIDIA Open Model
  License. Accept it on the HF model page, grab an `HF_TOKEN`, and store it as a Modal
  Secret: `modal secret create huggingface HF_TOKEN=hf_xxx`.
- **Reasoning parser** — replace `nano_v3_reasoning_parser.py` with the real plugin from
  the vLLM Nemotron-3-Nano recipe (or set `USE_REASONING_PLUGIN=False` in `modal_app.py`
  if your pinned vLLM ships `nano_v3` built-in). See `../docs/COSTS.md` deploy flags.
- **Config** — `cp .env.example .env` and fill it in. `.env` is git-ignored.
- **Doorway deps** — `inference_local.py` needs `openai` + `python-dotenv`:
  `pip install -r requirements.txt`. No venv is checked in, so if you'd rather not touch
  system python, run it throwaway:
  `uv run --no-project --with 'openai>=1.40' --with 'python-dotenv>=1.0' python inference_local.py`

## 1. Deploy the server (laptop)

```bash
bash modal-deploy.sh          # MODAL_GPU_PROFILE in .env picks the GPU/precision
```

It runs `modal deploy modal_app.py` and prints a web-endpoint URL. Profiles (see `.env`):

| MODAL_GPU_PROFILE | GPU | Model | When |
|-------------------|-----|-------|------|
| `a100-bf16` *(default)* | A100 80 GB | Nano BF16, 256k ctx | **the judged path** — ~$2.50/hr, cold start ~1–2 min |
| `l40s-fp8` | L40S 48 GB | Nano FP8, 128k ctx | dev/bulk — faster *and* cheaper to run, but ~12 min cold start |

> Both profiles are measured (`../docs/THROUGHPUT.md`). L40S/FP8 wins on throughput and
> price (865 vs 696 tok/s at C=16, $1.95 vs $2.50/hr) and loses on **cold-start recovery**:
> its vLLM engine init takes 494–602s versus the A100's 29s. The default is set for the
> demo, where a preemption on L40S would mean ~12 minutes of dead air.

> Scale-to-zero means you only spend the free monthly credit while a request is actually
> running. Intermittent dev over a weekend is single-digit GPU-hours.

## 2. Wire `inference.local` and verify

Paste the URL Modal printed into `.env` (append `/v1`), then:

```bash
bash verify.sh              # models + chat + tool-call all green
python inference_local.py   # same check, through the doorway client → AIRTIGHT-OK
```

Set `INFERENCE_BASE_URL=https://<workspace>--airtight-nemotron-serve.modal.run/v1`. The
*name* is what the rest of the system pins to.

**`inference.local` now has a real gateway process (A4).** `inference_gateway.py` fronts the
name, holds the provider key host-side, injects it, and pins the model — so the sandbox
carries only a dummy token:

```bash
# host side (holds the real key): fronts the operator's chosen upstream
INFERENCE_BACKEND=modal MODAL_BASE_URL=... MODAL_API_KEY=... \
    python -m runtime.inference_gateway --port 8900
echo '127.0.0.1 inference.local' | sudo tee -a /etc/hosts   # one-line name mapping
python -m runtime.gateway_smoke        # offline proof, no GPU: 5 green checks
```

Then the agent points at it with `INFERENCE_BACKEND=gateway` +
`INFERENCE_GATEWAY_URL=http://inference.local/v1` and **no provider key at all**. What's
still outstanding is A1's Landlock/seccomp isolation (Linux) that makes "the sandbox cannot
reach the key by any other path" an *enforced* guarantee rather than a configuration fact.

Both scripts honor pre-set env, so you can smoke-test a backend without editing `.env`:

```bash
INFERENCE_BACKEND=nim bash verify.sh    # exported vars win over .env
```

## 3. Keep it warm for the demo / stop the meter

```bash
MODAL_MIN_CONTAINERS=1 bash modal-deploy.sh   # pin one warm replica for the judged run
MODAL_MIN_CONTAINERS=0 bash modal-deploy.sh   # back to scale-to-zero (stops idle billing)
```

Cold start is **~1–2 min on `a100-bf16`** (the default) and **~12 min on `l40s-fp8`** —
measured, with the Volume warm either way (`../docs/THROUGHPUT.md`). Pin a replica only for
the demo window, and pin it at **T-minus 15**, not T-minus 5.

## 4. Fallback — the free NIM endpoint (no GPU)

If Modal is cold, credits run out, or you just want a free dev endpoint, flip to the
hosted NVIDIA NIM endpoint — **one env var**, no code:

```bash
INFERENCE_BACKEND=nim      # in runtime/.env — that's the whole flip
bash serve-nim.sh          # proves it: runs verify.sh against NIM, checks .env never moved
```

Your Modal values are untouched by the flip, so coming back is `INFERENCE_BACKEND=modal`.
Needs a free `nvapi-...` key in `NVIDIA_API_KEY` (https://build.nvidia.com, no card).

A hosted API does **not** count toward the vLLM bounty (that's the Modal path); this is
purely the safety net. There is **no automatic failover** — falling back is an operator
action, so a judged run can never silently land on a hosted endpoint.

---

## The invariant, restated

`inference_local.py` reads its endpoint from operator env and exposes **no** way for the
agent to point elsewhere. Reasoning is **off** by default (deterministic tool calls), on
only for drafting. Lane B fills the `_guard_inbound` / `_guard_outbound` seam with
HiddenLayer `interactions.analyze(...)`. Keep both true and the security + containment
stories keep converging on this one hop.
