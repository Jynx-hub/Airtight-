# inference.local — the one boundary

The single most load-bearing decision in Airtight, on one page. Everything (HiddenLayer, OpenShell, vLLM, the Nemotron constraint) converges here.

## What it is

The agent never talks to a model provider directly. Every inference call addresses **`inference.local`**, a virtual host intercepted by the **OpenShell gateway** on the host. The gateway resolves it to whatever backend the *operator* configured. Provider credentials live on the host — never inside the sandbox.

**The invariant (do not break):** the operator chooses the model endpoint, never the agent. Any change that lets the agent pick its own endpoint breaks the security story, the containment story, and the bounty story simultaneously.

## The wiring

```
agent (in OpenShell sandbox)
  └─ OpenAI-compatible call → https://inference.local/v1
       └─ OpenShell gateway (host side; dynamic policy, hot-reloadable)
            │  ◐ A4 (code side) BUILT: runtime/inference_gateway.py is a real
            │    process that fronts `inference.local`, injects the provider key
            │    host-side, and pins the model. Point the agent at it with
            │    INFERENCE_BACKEND=gateway. Verified offline (runtime/gateway_smoke.py).
            │    Still on A1: the Landlock/seccomp *isolation* (Linux) that makes
            │    host-side creds an enforced guarantee, and the /etc/hosts mapping.
            ├─ PRIMARY:  vLLM on Modal (serverless, free tier)
            │            Nemotron 3 Nano (guaranteed — L40S/FP8 fits VRAM)
            │            Nemotron 3 Super (only if a bigger box lands)
            └─ FALLBACK: NVIDIA NIM free hosted endpoint
                         nvidia/nemotron-3-nano-30b-a3b
```

- **vLLM** stands up the OpenAI-compatible server: `vllm serve <model>`, deployed to Modal via `runtime/modal_app.py` (exact flags: check the vLLM Nemotron 3 cookbook, `research/vllm.md`). Continuous batching is why it's here — the heartbeat fans out concurrent Nano retrieval sub-agents (`agent/subagents.py`), and that's exactly vLLM's workload.
- **Both backends are remote.** The no-local-hardware rule holds either way; only the *local* Ollama/vLLM path from `research/nemoclaw-openshell.md` §7 is off-limits.
- The OpenShell **inference tier** is dynamic policy: repointing the backend is a host-side config reload, not an agent action and not a redeploy.

## Backend selection — the one flip (F3)

One env var picks the backend. Both credential sets live in `runtime/.env` side by side, so flipping never destroys the other one's key and flipping back is the same single edit.

| `INFERENCE_BACKEND` | Backend | Bounty |
|---|---|---|
| `modal` | **PRIMARY** — self-hosted vLLM on Modal | ✅ counts for the $500 vLLM bounty |
| `nim` | **FALLBACK** — NVIDIA's free hosted endpoint | ❌ hosted; does not count |
| `gateway` | agent → host-side `inference.local` gateway (dummy token; real key injected host-side, A4). The gateway's *own* backend is `modal`/`nim` | inherits the gateway's upstream |
| unset | legacy: the flat `INFERENCE_*` vars, exactly as before F3 | — |

NIM's base URL and model slug are public constants baked into `runtime/inference_local.py`; only `NVIDIA_API_KEY` comes from env. That is what makes this **one** variable instead of three — the pre-F3 flip overwrote `INFERENCE_API_KEY` with the `nvapi-` key and lost the Modal credential in the process.

**There is no automatic failover, by design.** A silent hop to a hosted endpoint mid-demo would swap the judged self-hosted path for one that earns nothing, quietly voiding the bounty evidence. Falling back is an operator act. `reload_backend()` in the doorway is the operator-only hot-reload — it takes no arguments and nothing in `chat()` calls it, so the agent cannot use it to repoint anything. The OpenShell gateway supersedes it at F5.

Prove the flip end-to-end with `bash runtime/serve-nim.sh` — it runs `verify.sh` against NIM and fingerprints `runtime/.env` before and after to prove it never writes it.

## Why one hop wins four prizes

Because inference is pinned to a single operator-owned hop, four separate judging stories sit on the *same* enforcement point instead of four leaky ones:

| Prize | What sits on the hop |
|---|---|
| HiddenLayer track | the AIDR bus analyzes every prompt/response crossing it |
| NemoClaw/OpenShell track | the inference tier pins it; the agent cannot exfiltrate to an arbitrary model endpoint |
| Nemotron constraint | the pinned backend *is* Nemotron — all-open-model by construction |
| vLLM bounty | the pinned backend is vLLM-served — real integration, not decoration |

## The shared doorway (code contract)

All application code calls **one shared inference function** — the "shared doorway" from `docs/WORKSTREAMS.md` setup step 1. Rules:

1. No raw model calls anywhere. Every call goes through the doorway; the doorway calls `inference.local`.
2. The HiddenLayer `interactions.analyze()` wrapper lives inside the doorway — bypassing the doorway bypasses the bus, which is a bug by definition.
3. The doorway sets the reasoning mode per turn type: reasoning-OFF / capped thinking budget on tool-call turns (deterministic function calling), reasoning-ON for claim drafting and loophole analysis.
4. Model name, base URL, and API key come from operator config/env — never from agent-visible state.
5. Until M1b lands, the doorway may run as a stub that returns "all clear" so downstream lanes can build (WORKSTREAMS setup tip).
6. Falling back to NIM is an **operator action, never automatic and never agent-triggerable**. NIM is hosted; it does not count toward the vLLM bounty.

## Known gaps — status (A4 landed 2026-07-18, code side)

Written down so nobody over- *or* under-claims during judging:

- **`inference.local` gateway process — BUILT (`runtime/inference_gateway.py`).** A real,
  stdlib-only OpenAI-compatible process now fronts the name and forwards to the
  operator-pinned upstream (reusing the one `_resolve()` table, so `modal|nim` still
  selects the destination). Point the agent at it with `INFERENCE_BACKEND=gateway`.
  **Still outstanding:** the literal name→process mapping is a one-line operator step
  (`127.0.0.1 inference.local` in `/etc/hosts`), and in production the gateway runs on the
  host *outside* the OpenShell sandbox — which needs **A1** (Linux).
- **Provider credentials host-side — DONE and verified offline.** With
  `INFERENCE_BACKEND=gateway` the sandbox holds only a dummy token; the real key lives in
  the gateway process's env and is injected host-side. `runtime/gateway_smoke.py` proves it
  with three real processes: the dummy token is rejected talking to the provider directly
  (401) yet works through the gateway (200), and the provider key never appears in the
  agent's environment. **What A1 still adds:** the Landlock/seccomp isolation that makes
  "the sandbox *cannot* obtain the key by any other path" an enforced guarantee rather than
  a configuration fact.

## Verify at M1b

- The endpoint answers OpenAI-compatible requests from inside the sandbox via `inference.local`.
- Concurrent sub-agent requests actually batch (throughput under the heartbeat, not one-at-a-time).
- The OpenShell egress route to the vLLM host is on the allowlist, and the agent cannot repoint it. With NIM live as a fallback, that allowlist needs **two** destinations, not one.
- The one-var NIM flip is proven (`bash runtime/serve-nim.sh`) and `runtime/.env` is byte-identical afterward.

Detail: `research/vllm.md` (serving, VRAM, Modal) · `docs/COSTS.md` (free-tier plan) · `research/nemoclaw-openshell.md` §7 (gateway, routing policy) · `research/nemotron.md` (model choice, reasoning toggle).
