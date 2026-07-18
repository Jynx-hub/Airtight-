# inference.local — the one boundary

The single most load-bearing decision in Airtight, on one page. Everything (HiddenLayer, OpenShell, vLLM, the Nemotron constraint) converges here.

## What it is

The agent never talks to a model provider directly. Every inference call addresses **`inference.local`**, a virtual host intercepted by the **OpenShell gateway** on the host. The gateway resolves it to whatever backend the *operator* configured. Provider credentials live on the host — never inside the sandbox.

**The invariant (do not break):** the operator chooses the model endpoint, never the agent. Any change that lets the agent pick its own endpoint breaks the security story, the containment story, and the bounty story simultaneously.

## The wiring

```
agent (in OpenShell sandbox)
  └─ OpenAI-compatible call → https://inference.local
       └─ OpenShell gateway (host side; dynamic policy, hot-reloadable)
            ├─ PRIMARY:  vLLM serve on a rented Brev GPU
            │            Nemotron 3 Nano (guaranteed — fits VRAM)
            │            Nemotron 3 Super (only if the GPU allows)
            └─ FALLBACK: NVIDIA NIM cloud API
                         nvidia/nemotron-3-super-120b-a12b
```

- **vLLM** stands up the OpenAI-compatible server: `pip install vllm && vllm serve <model>` on the Brev box (exact flags: check the vLLM Nemotron 3 cookbook, `research/vllm.md`). Continuous batching is why it's here — the heartbeat fans out concurrent Nano retrieval sub-agents, and that's exactly vLLM's workload.
- **Both backends are remote.** The no-local-hardware rule holds either way; only the *local* Ollama/vLLM path from `research/nemoclaw-openshell.md` §7 is off-limits.
- The OpenShell **inference tier** is dynamic policy: repointing the backend is a host-side config reload, not an agent action and not a redeploy.

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

## Verify at M1b

- The endpoint answers OpenAI-compatible requests from inside the sandbox via `inference.local`.
- Concurrent sub-agent requests actually batch (throughput under the heartbeat, not one-at-a-time).
- The OpenShell egress route to the vLLM host is on the allowlist, and the agent cannot repoint it.

Detail: `research/vllm.md` (serving, VRAM, Brev) · `research/nemoclaw-openshell.md` §7 (gateway, routing policy) · `research/nemotron.md` (model choice, reasoning toggle).
