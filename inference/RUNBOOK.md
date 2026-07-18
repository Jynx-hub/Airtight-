# Inference runbook (Person 2)

Owns: the Modal vLLM deployment, `inference.local` routing, and keeping the endpoint alive through judging. Background: `docs/INFERENCE-LOCAL.md`, `research/vllm.md`. Serving template: `inference/vllm_modal.py`.

## 1. Deploy vLLM on Modal (F1)

Modal is serverless GPU — you define the server in code and deploy it; there's no box to SSH into or babysit. The template is `inference/vllm_modal.py`.

```bash
pip install modal
modal setup                                  # one-time auth (opens a browser)
modal deploy inference/vllm_modal.py         # builds the image, deploys, prints the URL
```

Deploy prints an HTTPS URL like `https://<workspace>--airtight-vllm-serve.modal.run`. That is the endpoint. Use `modal serve …` instead for a hot-reload dev URL while you tune flags.

- **Nano first, always.** `nvidia/nemotron-3-nano-31b-a3b` on one A100-80GB is the guaranteed path (set in the template). Try Super (`nvidia/nemotron-3-super-120b-a12b`, `gpu="H200:2"`) only if VRAM allows — even at ~12.7B active it must hold all 120B params. Don't burn hours on it.
- **Credits.** Modal's free tier includes monthly compute credit; apply for startup credits if we need more. `scaledown_window` + scale-to-zero mean you only pay while serving — but keep `min_containers=1` during the demo so there's no cold start on stage.
- **UNVERIFIED, fix in the template only:** the web-server decorator name, GPU flag spellings, and the vLLM/Nemotron serve flags (`--tool-call-parser nemotron`). Confirm against Modal's vLLM example (https://modal.com/docs/examples/vllm_inference) and the vLLM Nemotron 3 cookbook (https://vllm.ai/blog/2026-03-11-nemotron-3-super).

## 2. Verify + capture bounty numbers (F2)

```bash
python inference/verify_endpoint.py --base-url https://<workspace>--airtight-vllm-serve.modal.run/v1
```

Checks OpenAI compatibility (`/v1/models`, chat, streaming), then fires concurrent requests and prints throughput. **Save the concurrency numbers** — "N concurrent requests, X req/s, continuous batching" is the vLLM-bounty evidence. Run it once with `--concurrency 1` and once with `--concurrency 16` for a before/after. Modal autoscaling under concurrent load is itself part of the story.

The script also prints the served model list — if the ID differs from `AIRTIGHT_MODEL` in `.env.example`, fix it there and tell the team.

## 3. Hand off to the team (F4)

Post in the team channel: the base URL, the confirmed model ID, and the throughput numbers. Everyone sets:

```
AIRTIGHT_MODE=live
AIRTIGHT_BASE_URL=https://<workspace>--airtight-vllm-serve.modal.run/v1
AIRTIGHT_MODEL=<confirmed id>
```

## 4. Fallback: NIM cloud (one config flip)

If the Modal deploy misbehaves, the team flips to the NVIDIA NIM cloud API — no code change:

```
AIRTIGHT_BASE_URL=https://integrate.api.nvidia.com/v1   # UNVERIFIED path — confirm at build.nvidia.com
AIRTIGHT_API_KEY=<NIM key from build.nvidia.com>
AIRTIGHT_MODEL=nvidia/nemotron-3-super-120b-a12b
```

Verify with the same script: `python inference/verify_endpoint.py --base-url <NIM url> --api-key <key>`. (Note: NIM is a hosted API, not self-hosted vLLM, so this fallback does not count toward the vLLM bounty — it's the reliability net, not the primary path.)

## 5. Endpoint down — bring it back

Modal is serverless, so there's no instance to restart — you redeploy:

1. `modal deploy inference/vllm_modal.py` again (cached weights on the HF Volume make the rebuild fast).
2. Check `modal app list` / `modal app logs airtight-vllm` for the deploy status.
3. Re-run the verify script; the URL is stable across redeploys, so no need to repost it.
4. If it won't come back inside 10 minutes, call the fallback (§4) and move on.

## 6. In-sandbox routing (with Person 4, at M1)

Inside the OpenShell sandbox the agent calls `https://inference.local/v1`; the gateway forwards to the Modal URL with creds held host-side. Policy draft: `inference/policy/airtight-sandbox.yaml` · onboarding steps: `inference/policy/ONBOARDING.md`. The same verify script validates the in-sandbox route: `--base-url https://inference.local/v1`.
