# Research — HiddenLayer Runtime Security (for Airtight)

*Verified 2026-07-17. Sources = HiddenLayer's own docs + official Python SDK, cross-checked against LiteLLM & TrueFoundry gateway integrations.*

## 1. Product naming (this trips people up)
There is **no product literally called "Runtime Security API" or "Prompt Analyzer."** The naming stacks:

- **AISec Platform** = umbrella product (four pillars: AI Discovery, AI Supply Chain Security, **AI Runtime Security**, AI Attack Simulation). AISec Platform 2.0 shipped April 2025.
- **AI Runtime Security** = the pillar you want — real-time input/output monitoring for hosted/custom LLMs.
- **AIDR (AI Detection & Response)** = the detection *engine*. The GenAI variant appears in docs URLs as `aidr-g`.
- **Interactions** = the actual **API** you call: "a flexible API that takes a prompt input and/or model output and returns a detailed analysis for many detection categories." SaaS or self-hosted container.
- **Model Scanner** is a *different* product (scans model artifacts for supply-chain threats) — **not** runtime input/output. Don't cite it for inline detection.

**Bottom line:** the real-time input/output detection product is **"AI Runtime Security," powered by the AIDR engine, consumed through the Interactions API.**

## 2. What it detects
`analysis[]` categories (each toggled by your Project's ruleset): **prompt_injection** (direct + indirect, `scan_type: "full"`), **jailbreaks/guardrails**, **PII**, **code** (malicious/unwanted, in/out), **denial of service (DoS)**, **block_list** (custom deny terms), **model refusals**, **prompt language**. Agent-level additions: unsafe tool use / agentic misuse, data leakage/exposure.

## 3. API shape (endpoint + request/response)
Two endpoint generations exist in the wild — flag this before hardcoding:
- **Direct Interactions endpoint:** `POST /detection/v1/interactions` (LiteLLM integration; matches SDK `interactions.analyze()`).
- **v2 detection endpoints** (TrueFoundry gateway): `POST /detection/v2/*` split into `interaction-evaluations` (in/out validation), `request-evaluations` (input redaction), `response-evaluations` (output redaction).

**Base URLs (SaaS):** `https://api.hiddenlayer.ai` (US) / `https://api.eu.hiddenlayer.ai` (EU). Self-hosted: your own `HIDDENLAYER_API_BASE`.

**Request body (shape):**
```json
{
  "metadata": { "model": "gpt-4o", "requester_id": "user-1234" },
  "input": { "messages": [ { "role": "user", "content": "…prompt text…" } ] }
}
```
Headers: `hl-project-id: <PROJECT_ID>` (scopes to your ruleset), optionally `hl-requester-id`. Pass the prompt (input phase) and/or the model output (output phase).

**Response body (docs-derived):**
```json
{
  "metadata": {
    "event_id": "d290f1ee-6c54-4b01-90e6-d701748f0851",
    "analyzed_at": "2023-10-10T14:48:00.000Z",
    "provider": "openai", "model": "gpt-5", "requester_id": "user-1234",
    "project": { "project_id": "…", "project_alias": "enterprise-search", "ruleset_id": "…" },
    "processing_time_ms": 15.34
  },
  "analysis": [
    {
      "name": "prompt_injection", "phase": "input", "version": "5",
      "detected": false,
      "configuration": { "enabled": true, "scan_type": "full" },
      "findings": { "frameworks": {}, "matches": [] },
      "processing_time_ms": 0.005,
      "id": "prompt_injection.5.input"
    }
  ]
}
```

**Fields to design against:** `analysis[]` is the detections array; each entry has `name` (category), `phase` ("input"/"output"), **`detected`** (boolean — your per-category verdict), `findings.matches`, per-analyzer `processing_time_ms`. Top-level correlator is `metadata.event_id`. **There is no single top-level scalar `verdict`/`confidence`** — you derive allow/block from `detected` flags across the array.

**Policy/verdict mapping** (how gateways turn `analysis` into a decision): HiddenLayer's `outcome.action` ∈ `NONE` (pass), `DETECT` (flag), `REDACT` (sanitize body), `BLOCK` (deny). Gateways map DETECT/REDACT/BLOCK → deny/transform. If you build enforcement yourself, replicate that contract. **← This is the source of Airtight's response-policy table.**

## 4. Auth
**OAuth2 client-credentials** (SaaS): `HIDDENLAYER_CLIENT_ID` + `HIDDENLAYER_CLIENT_SECRET` (AISec Console → API Keys) exchanged at `https://auth.hiddenlayer.ai` for a short-lived **Bearer token** → `Authorization: Bearer <token>`. Python SDK can shortcut with a pre-minted `HIDDENLAYER_TOKEN`. Self-hosted skips OAuth (point at `HIDDENLAYER_API_BASE`). Every call carries `hl-project-id`.

## 5. Latency
No published SLA, but the payload reports `processing_time_ms` ≈ 15 ms end-to-end, individual analyzers sub-millisecond (0.005 ms). Real inline cost = that + network RTT to region — hence the **locally-hosted container** and gateway defaults of **fail-open** (`HIDDENLAYER_FAIL_OPEN_ON_UNAVAILABLE=true`, `HIDDENLAYER_TIMEOUT_SECONDS=10`). For a latency-sensitive inline hop, self-host or use the async output-phase call. **For Airtight's security demo, run fail-CLOSED on the ingested-doc + tool-call hops.**

## 6. Official SDK
- **Python: `pip install hiddenlayer-sdk`** (3.9+, sync + async via httpx). Repo `github.com/hiddenlayerai/hiddenlayer-sdk-python`.
  ```python
  from hiddenlayer import HiddenLayer
  client = HiddenLayer(environment="prod-us")   # or "prod-eu"
  resp = client.interactions.analyze(
      metadata={"model": "gpt-4o", "requester_id": "user-1234"},
      input={"messages": [{"role": "user", "content": "…"}]},
  )
  print(resp.analysis)
  ```
- **JS/TS:** no first-party SDK surfaced — docs point to the REST API. Treat "official JS SDK" as unconfirmed; call REST from Node.

## Caveats to carry into the build
- The `/detection/v1` vs `/detection/v2/*` split is real — **confirm the current path in the login-gated Developer Portal** before hardcoding; v2 is what newer gateways target.
- No scalar `verdict`/`confidence` in the documented response — compute from per-category `detected` + `outcome.action`. If you need numeric per-detection confidence, verify in the Developer Portal.
- Canonical full schema / OpenAPI sits behind the Developer Portal login; shapes above assembled from public docs example + SDK + two independent gateway integrations.

## Sources
1. AI Runtime Security — https://www.hiddenlayer.com/platform/ai-runtime-security
2. Interactions (Console docs) — https://docs.hiddenlayer.ai/docs/products/console/runtime_protection_interactions
3. Getting Started with Interactions SaaS (AIDR-G) — https://docs.hiddenlayer.ai/docs/products/aidr-g/interactions/interactions
4. HiddenLayer Guardrails — LiteLLM — https://docs.litellm.ai/docs/proxy/guardrails/hiddenlayer
5. HiddenLayer — TrueFoundry AI Gateway — https://www.truefoundry.com/docs/ai-gateway/hiddenlayer
6. hiddenlayer-sdk — https://pypi.org/project/hiddenlayer-sdk/ · https://github.com/hiddenlayerai/hiddenlayer-sdk-python
7. AISec Platform 2.0 announcement (Apr 2025) — PR Newswire
