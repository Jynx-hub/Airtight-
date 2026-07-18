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
4. Wire inference: the gateway resolves `inference.local` → Person 2's vLLM URL (creds host-side). Verify from inside the sandbox:
   ```bash
   python inference/verify_endpoint.py --base-url https://inference.local/v1
   ```
5. Run the agent smoke inside the sandbox: `AIRTIGHT_MODE=live AIRTIGHT_BASE_URL=https://inference.local/v1 python -m agent.run_smoke`.
6. After the audit log shows the real egress set, flip each `enforcement: audit` → `enforce` and hot-reload (`openshell policy set ... --wait`). Denials now 403 into the Policy Advisor flow:
   ```bash
   openshell rule get airtight --status pending        # UNVERIFIED
   openshell rule approve airtight --chunk-id <id>
   openshell rule reject  airtight --chunk-id <id> --reason "no external backup of client IP"
   ```

## Things to confirm on the day

- Exact repo paths + CLI verbs (`nemoclaw onboard`, `openshell sandbox create`, `openshell policy set`, `openshell rule ...`) — early preview, may have changed.
- Policy schema field names against `docs.nvidia.com/openshell/reference/policy-schema` (our draft follows the researched schema; `blueprint.yaml` / `openclaw-sandbox.yaml` file names are conceptual).
- That the gateway lets us point `inference.local` at an *external* vLLM host (the Modal endpoint) rather than the default NIM route.
- The in-sandbox URL shape (`https://inference.local/v1` vs a port variant) — the doorway treats it as an opaque env string, so any shape works.

## Plan B (if the preview won't stand up)

Reproduce the same graded architecture on any remote Linux host — gVisor/Firecracker sandbox + OPA/Rego egress gate + a NIM proxy + a manual approve step — and describe it in NemoClaw's four-tier vocabulary (filesystem / process / network / inference). Details: `research/nemoclaw-openshell.md` §8. The judging story survives intact.
