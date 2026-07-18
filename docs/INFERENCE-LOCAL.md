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
            │  ⚠ F5 — NOT BUILT YET. Today the operator-pinned Modal URL in
            │    runtime/.env *is* `inference.local`; the name is a contract,
            │    not a resolvable host.
            ├─ PRIMARY:  vLLM on Modal (serverless, free tier)
            │            Nemotron 3 Nano (guaranteed — L40S/FP8 fits VRAM)
            │            Nemotron 3 Super (only if a bigger box lands)
            └─ FALLBACK: NVIDIA NIM free hosted endpoint
                         nvidia/nemotron-3-nano-30b-a3b
```

- **vLLM** stands up the OpenAI-compatible server: `vllm serve <model>`, deployed to Modal via `runtime/modal_app.py` (exact flags: check the vLLM Nemotron 3 cookbook, `research/vllm.md`). Continuous batching is why it's here — the heartbeat fans out concurrent Nano retrieval sub-agents, and that's exactly vLLM's workload.
- **Both backends are remote.** The no-local-hardware rule holds either way; only the *local* Ollama/vLLM path from `research/nemoclaw-openshell.md` §7 is off-limits.
- The OpenShell **inference tier** is dynamic policy: repointing the backend is a host-side config reload, not an agent action and not a redeploy.

## Backend selection — the one flip (F3)

One env var picks the backend. Both credential sets live in `runtime/.env` side by side, so flipping never destroys the other one's key and flipping back is the same single edit.

| `INFERENCE_BACKEND` | Backend | Bounty |
|---|---|---|
| `modal` | **PRIMARY** — self-hosted vLLM on Modal | ✅ counts for the $500 vLLM bounty |
| `nim` | **FALLBACK** — NVIDIA's free hosted endpoint | ❌ hosted; does not count |
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

## Known gaps (as of F3)

Written down so nobody claims them during judging:

- **`inference.local` is a naming contract, not a resolvable host.** No `/etc/hosts` entry, no DNS, no gateway process exists. Every call resolves through the operator-pinned URL in `runtime/.env`. The invariant it protects — the agent cannot choose its own endpoint — *is* enforced today, in `inference_local.py`; only the literal hostname is outstanding. Closes at **F5**.
- **Provider credentials are read inside the sandbox.** `inference_local.py` loads the API key from `runtime/.env`, so the "creds live on the host, never inside the sandbox" promise above is not yet true. It becomes true when the F5 gateway injects credentials host-side and the sandbox holds none.

## Verify at M1b

- The endpoint answers OpenAI-compatible requests from inside the sandbox via `inference.local`.
- Concurrent sub-agent requests actually batch (throughput under the heartbeat, not one-at-a-time).
- The OpenShell egress route to the vLLM host is on the allowlist, and the agent cannot repoint it. With NIM live as a fallback, that allowlist needs **two** destinations, not one.
- The one-var NIM flip is proven (`bash runtime/serve-nim.sh`) and `runtime/.env` is byte-identical afterward.

Detail: `research/vllm.md` (serving, VRAM, Modal) · `docs/COSTS.md` (free-tier plan) · `research/nemoclaw-openshell.md` §7 (gateway, routing policy) · `research/nemotron.md` (model choice, reasoning toggle).
