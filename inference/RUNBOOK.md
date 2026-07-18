# Inference runbook (Person 2)

Owns: the Brev GPU, the vLLM server, `inference.local` routing, and keeping the box alive through judging. Background: `docs/INFERENCE-LOCAL.md`, `research/vllm.md`.

## 1. Stand up vLLM on Brev (F1)

1. Rent a GPU at brev.dev ($100 credits per team member from the NemoClaw + Nemotron bounties). One A100/H100-class GPU is enough for Nano. SSH in.
2. Install and serve:

```bash
pip install vllm

# UNVERIFIED: exact model ID and flags — confirm against the vLLM Nemotron 3
# cookbook (link below) and the server's own /v1/models before handing off.
vllm serve nvidia/nemotron-3-nano-31b-a3b \
  --host 0.0.0.0 --port 8000 \
  --enable-auto-tool-choice \
  --tool-call-parser nemotron    # UNVERIFIED flag name — check cookbook
```

3. **Nano first, always.** It is the guaranteed path. Try Super (`nvidia/nemotron-3-super-120b-a12b`) only if VRAM allows — even at ~12.7B active it must hold all 120B params. Don't burn hours on it.
4. Cookbook: "Run Highly Efficient and Accurate Multi-Agent AI with Nemotron 3 Super Using vLLM" — https://vllm.ai/blog/2026-03-11-nemotron-3-super (serve flags, chat template, tool-call parser, streaming configs).

## 2. Verify + capture bounty numbers (F2)

```bash
python inference/verify_endpoint.py --base-url http://<brev-ip>:8000/v1
```

Checks OpenAI compatibility (`/v1/models`, chat, streaming), then fires concurrent requests and prints throughput. **Save the concurrency numbers** — "N concurrent requests, X req/s, continuous batching" is the vLLM-bounty evidence. Run it once with `--concurrency 1` and once with `--concurrency 16` so we have a before/after.

The script also prints the served model list — if the ID differs from `AIRTIGHT_MODEL` in `.env.example`, fix it there and tell the team.

## 3. Hand off to the team (F4)

Post in the team channel: the base URL, the confirmed model ID, and the throughput numbers. Everyone sets:

```
AIRTIGHT_MODE=live
AIRTIGHT_BASE_URL=http://<brev-ip>:8000/v1
AIRTIGHT_MODEL=<confirmed id>
```

## 4. Fallback: NIM cloud (one config flip)

If the box misbehaves, the team flips to the NVIDIA NIM cloud API — no code change:

```
AIRTIGHT_BASE_URL=https://integrate.api.nvidia.com/v1   # UNVERIFIED path — confirm at build.nvidia.com
AIRTIGHT_API_KEY=<NIM key from build.nvidia.com>
AIRTIGHT_MODEL=nvidia/nemotron-3-super-120b-a12b
```

Verify with the same script: `python inference/verify_endpoint.py --base-url <NIM url> --api-key <key>`.

## 5. Box died — bring it back

1. Brev console → restart the instance (or rent a fresh one).
2. Re-run the `vllm serve` command from §1 (keep it in your shell history / a tmux session so it survives SSH drops: `tmux new -s vllm`).
3. Re-run the verify script; repost the base URL if the IP changed.
4. If it won't come back inside 10 minutes, call the fallback (§4) and move on.

## 6. In-sandbox routing (with Person 4, at M1)

Inside the OpenShell sandbox the agent calls `https://inference.local/v1`; the gateway forwards to your vLLM URL with creds held host-side. Policy draft: `inference/policy/airtight-sandbox.yaml` · onboarding steps: `inference/policy/ONBOARDING.md`. The same verify script validates the in-sandbox route: `--base-url https://inference.local/v1`.
