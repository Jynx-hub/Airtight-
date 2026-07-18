# M1 sandbox onboarding (hosted DGX Spark)

Stand up the NemoClaw/OpenShell sandbox **remotely** — nothing runs on a laptop (`docs/WORKSTREAMS.md` §A1). OpenShell needs Linux (Landlock + seccomp), so this happens on the hosted run pages, not macOS.

**Every CLI verb below is from `research/nemoclaw-openshell.md` (early preview, 2026-03). Tagged UNVERIFIED — confirm each against the live repo/docs before relying on it.**

## Steps

1. Open the hosted run pages: `build.nvidia.com/spark/nemoclaw` and `build.nvidia.com/spark/openshell`.
2. Install + onboard *(UNVERIFIED verbs)*:
   ```bash
   curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
   nemoclaw onboard          # wizard: creates the named assistant/sandbox
   nemoclaw list
   nemoclaw airtight status
   ```
3. Apply our policy *(UNVERIFIED verbs; validate the schema first — file: `airtight-sandbox.yaml`)*:
   ```bash
   openshell sandbox create --policy inference/policy/airtight-sandbox.yaml -- agent
   openshell policy set airtight --policy inference/policy/airtight-sandbox.yaml --wait
   openshell logs airtight --tail --source sandbox     # watch what the agent tries (audit mode)
   ```
4. Wire inference — **A4 gateway is already built and verified offline** (`runtime/inference_gateway.py`, proof `python -m runtime.gateway_smoke`). On the host (outside the sandbox), run it holding the real provider key, then map the name:
   ```bash
   INFERENCE_BACKEND=modal MODAL_BASE_URL=<vLLM url> MODAL_API_KEY=<key> \
       python -m runtime.inference_gateway --port 8900          # host-side; injects creds
   echo '127.0.0.1 inference.local' | sudo tee -a /etc/hosts     # (host-side) name → gateway
   ```
   Inside the sandbox the agent carries **no** provider key — only `INFERENCE_BACKEND=gateway`
   and `INFERENCE_GATEWAY_URL=https://inference.local/v1`. Verify from inside the sandbox:
   ```bash
   python inference/verify_endpoint.py --base-url https://inference.local/v1
   ```
   > This is the credential-injection + name-resolution half. What running inside OpenShell
   > *adds* is the Landlock/seccomp isolation that makes "the sandbox cannot reach the key by
   > any other path" an enforced guarantee (A4's isolation half — A1 delivers it).
5. Run the agent smoke inside the sandbox: `AIRTIGHT_MODE=live AIRTIGHT_BASE_URL=https://inference.local/v1 python -m agent.run_smoke`.
6. **A5 · audit→enforce sweep** — with everything in `enforcement: audit`, read the real egress set the agent produces, THEN flip to enforce. Do not pre-flip: the sweep is what catches an un-covered egress path (the named top risk). The policy YAML ships all endpoints in `audit` for exactly this.
   ```bash
   openshell logs airtight --tail --source sandbox      # A5: observe every egress it tries
   # only after reviewing the log:
   #   flip each `enforcement: audit` → `enforce` in airtight-sandbox.yaml (A2), then hot-reload:
   openshell policy set airtight --policy inference/policy/airtight-sandbox.yaml --wait
   ```
7. Denials now 403 into the Policy Advisor flow — the **same flow the offline demo already exercises** end-to-end (`python -m containment.demo`: real `PolicyAdvisorClient.escalate`, approve *and* reject branches, A3/A6). On the box it becomes a real socket-level 403:
   ```bash
   openshell rule get airtight --status pending        # UNVERIFIED
   openshell rule approve airtight --chunk-id <id>
   openshell rule reject  airtight --chunk-id <id> --reason "no external backup of client IP"
   ```

## Sequence (what gates what)

`A1` (this doc, steps 1–4) → `A5` (step 6 sweep) → `A2` (flip to enforce + validate the YAML against the **live** schema, step 6). A3/A6 (the Policy Advisor demo) and A4's gateway code are **already done and verified offline** — on the box they graduate from `[SIM]` to real sockets, no new code.

## Things to confirm on the day

- Exact repo paths + CLI verbs (`nemoclaw onboard`, `openshell sandbox create`, `openshell policy set`, `openshell rule ...`) — early preview, may have changed.
- Policy schema field names against `docs.nvidia.com/openshell/reference/policy-schema` (our draft follows the researched schema; `blueprint.yaml` / `openclaw-sandbox.yaml` file names are conceptual).
- That the gateway lets us point `inference.local` at an *external* vLLM host (the Modal endpoint) rather than the default NIM route.
- The in-sandbox URL shape (`https://inference.local/v1` vs a port variant) — the doorway treats it as an opaque env string, so any shape works.

## Plan B (if the preview won't stand up)

Reproduce the same graded architecture on any remote Linux host — gVisor/Firecracker sandbox + OPA/Rego egress gate + a NIM proxy + a manual approve step — and describe it in NemoClaw's four-tier vocabulary (filesystem / process / network / inference). Details: `research/nemoclaw-openshell.md` §8. The judging story survives intact.
