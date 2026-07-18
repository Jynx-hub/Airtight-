# Airtight Runtime — Runbook

**The operator card for the model endpoint.** Two audiences, and most people are the first one:

- **You just want to call the model** (Data / Surface / Agent lanes) → §1 only. Two minutes, no cloud account.
- **You're running the endpoint on demo day** (Lane A / operator) → §2–§4.

Deep detail lives elsewhere: `README.md` (how it's built), `../docs/THROUGHPUT.md` (the numbers), `../docs/COSTS.md` (the money), `../docs/INFERENCE-LOCAL.md` (the contract).

---

## 1. Call the model (consumer quickstart)

You need **no Modal account, no Modal CLI, and no `HF_TOKEN`.** Those are deployer-only. You need the base URL, which is handed out **out of band** — ask Steven. It is deliberately not committed: this repo is public and the API key is in it, so a published URL would be an open endpoint burning a fixed GPU credit.

```bash
cd runtime
cp .env.example .env          # git-ignored
#   → paste the base URL you were given into INFERENCE_BASE_URL (keep the trailing /v1)
#   → paste a free nvapi-... key from build.nvidia.com into NVIDIA_API_KEY (fallback only)
pip install -r requirements.txt
bash verify.sh                # models + chat + tool-call, all three must be green
```

Then use the one doorway. Never construct your own client — every call goes through here, which is what lets HiddenLayer and OpenShell enforce on one hop:

```python
from inference_local import chat

r = chat([{"role": "user", "content": "..."}])            # reasoning OFF — deterministic tool calls
r = chat([...], tools=[...])                              # tool-calling
r = chat([...], reasoning=True, max_tokens=4096)          # ON — claim drafting / loophole analysis
print(r.choices[0].message.content)
```

`model=` is not your choice — the alias is `nemotron` and the operator decides what's behind it.

**If `verify.sh` hangs for a couple of minutes, that is normal** — the container is cold and waking. It is not an outage. (On the `l40s-fp8` profile this can be ~12 minutes; the default `a100-bf16` is ~1–2.) If it fails outright, check §4 before reporting a bug.

---

## 2. Demo day — the five lines

The endpoint scales to zero when idle, so a cold judged run would eat minutes of dead air on stage. Pin a replica before, unpin after.

```bash
modal app list                                      # 1. pre-flight: confirm no other session is live
MODAL_MIN_CONTAINERS=1 bash modal-deploy.sh         # 2. T-minus 15 min: pin one warm replica
bash verify.sh                                      # 3. confirm green BEFORE anyone is watching
#    ... the judged run ...
MODAL_MIN_CONTAINERS=0 bash modal-deploy.sh         # 4. unpin — this is the step people forget
modal app list                                      # 5. confirm nothing resident. The meter is off.
```

Notes that make the difference between this working and looking like it worked:

- **Use `bash modal-deploy.sh`, not bare `modal deploy`.** The script `cd`s correctly and loads `.env` *non-destructively*, so the inline `MODAL_MIN_CONTAINERS=1` actually wins. Before that fix, this exact command deployed scale-to-zero anyway — you'd believe you had a warm replica pinned for judging and you would not.
- **Step 4 is the named cost failure mode** (`../docs/COSTS.md`). A forgotten warm replica bills ~$1.95/hr against a fixed free credit until someone notices.
- **Step 1 is not ceremony.** A second session can wake, redeploy, or contaminate the endpoint mid-window; one benchmark run already recorded exactly that.
- **Cold start, measured 2026-07-18** — `a100-bf16` (the default, the judged profile): **~1–2 min**. `l40s-fp8`: **~12 min**, even with weights and compile cache warm. Do not switch profiles casually; see `../docs/THROUGHPUT.md` §Second profile.
- **Modal preempts containers.** It happened during the benchmark session. If the endpoint dies mid-demo it restarts automatically, but you eat a full cold start — which is exactly why the judged profile is the one that recovers in a minute, and why step 2 exists.

---

## 3. If Modal is down — flip to NIM

One variable. No code change.

```bash
#   in runtime/.env:
INFERENCE_BACKEND=nim         # ← the whole flip. modal ⇄ nim, both credential sets stay intact.
bash serve-nim.sh             # proves it end-to-end and checks .env never moved
```

A running process picks it up via `reload_backend()`; otherwise restart. Going back is `INFERENCE_BACKEND=modal`.

**Know what you're trading before you flip it:**

- NIM is **hosted**, so it does **not** count toward the $500 vLLM bounty. The Modal path is the judged one. This is break-glass, not an equivalent swap.
- NIM's free tier is **1,000 inference credits and 40 requests/minute**. The ablation fans out at concurrency 16 — sustained, that will rate-limit. Reduce fan-out before demoing on NIM.
- There is **no automatic failover, by design.** A silent mid-demo hop to a hosted endpoint would quietly void the bounty evidence. Falling back is a deliberate human act.

---

## 4. Known surprises

Things that look like bugs in your code and aren't:

- **Streaming returns empty `content`.** With reasoning off, the *streaming* path routes every token to `reasoning_content` and leaves `delta.content` empty. Non-streaming is fine, so the doorway's `chat()` is unaffected — this bites streaming UIs only. It's upstream: NVIDIA's own `nano_v3` parser overrides only the non-streaming method, and our copy is byte-identical to theirs. Workaround: read `delta.reasoning_content or delta.content`. Detail: `../docs/THROUGHPUT.md` §Open issue.
- **First call takes minutes.** Cold container. Expected — see §1.
- **`INFERENCE_BACKEND=nim` errors on an empty key.** By design; get a free `nvapi-...` at build.nvidia.com.
- **`inference.local` doesn't resolve.** It's currently a naming contract, not a host — no DNS, no gateway process yet. The invariant it protects (the agent can't choose its own endpoint) *is* enforced today in `inference_local.py`. The real gateway lands at F5.

---

## 5. Deployer only

```bash
bash modal-deploy.sh                    # deploy; MODAL_GPU_PROFILE in .env picks the hardware
python bench.py --warmup                # cold-start latency — the number §2 quotes
python bench.py --sweep --gpu "<label>" # the concurrency sweep / bounty evidence
python mock_endpoint.py --port 8001     # free offline fake — debug harnesses here FIRST
```

- **Validate against `mock_endpoint.py` before touching the live endpoint.** Debugging on a metered cold start is how the credit disappears.
- Swapping `MODAL_GPU_PROFILE` needs a redeploy (the profile is baked into the image), **but the endpoint URL does not change** — nobody downstream has to be told.
- `--max-num-seqs 16` in `modal_app.py` and `serve-vllm.sh` is load-bearing, not a tuning knob. The throughput curve knees at exactly 16, and "the knee lands on the pinned cap" is the bounty argument.
- **Pausing and un-pausing the Modal app is the operator's call.** Not an agent's, not a teammate's. GPU time is the scarcest resource on this project.
