# Research — NemoClaw + OpenShell (for Airtight)

*Verified 2026-07-17 against NVIDIA docs, GitHub, and independent write-ups. NemoClaw/OpenShell launched **early preview 2026-03-16** (after model training cutoff), so everything here is web-sourced, not prior knowledge — cross-consistent across independent origins.*

## Executive summary
Both projects are **real**. `NVIDIA/NemoClaw` and `NVIDIA/OpenShell` are real GitHub repos with docs at `docs.nvidia.com`, an NVIDIA Technical Blog series, and a `build.nvidia.com` (DGX Spark) presence. **OpenClaw** is also real — the always-on personal-agent framework (Peter Steinberger's project). NemoClaw wraps an agent (OpenClaw by default; also Hermes and LangChain Deep Agents Code) inside an **OpenShell** sandbox with managed inference.

**Key correction:** there is **no single `require_approval:` YAML key.** OpenShell's schema expresses allow/deny via `enforcement: enforce | audit`, and the human-in-the-loop / allow-with-escalation boundary comes from a separate subsystem, **Policy Advisor** (default-deny → agent proposes a rule → human approves out-of-band → hot-reload → agent retries). Judges will probe this distinction.

## 1. Confirmed repos & docs
| Thing | URL |
|---|---|
| NemoClaw repo | https://github.com/NVIDIA/NemoClaw |
| NemoClaw community examples | https://github.com/NVIDIA/nemoclaw-community |
| NemoClaw docs | https://docs.nvidia.com/nemoclaw/ |
| OpenShell repo | https://github.com/NVIDIA/OpenShell |
| OpenShell community base image / default policy | https://github.com/nvidia/openshell-community (`dev-sandbox-policy.yaml`) |
| **OpenShell Policy Schema reference** (key doc) | https://docs.nvidia.com/openshell/reference/policy-schema |
| OpenShell "Customize Sandbox Policies" | https://docs.nvidia.com/openshell/sandboxes/policies |
| OpenShell **Policy Advisor** (HITL) | https://docs.nvidia.com/openshell/sandboxes/policy-advisor |
| OpenShell security best practices | https://docs.nvidia.com/openshell/security/best-practices |
| NVIDIA Technical Blog (build guide) | https://developer.nvidia.com/blog/build-a-secure-always-on-local-ai-agent-with-nvidia-nemoclaw-and-openclaw/ |
| DGX Spark run pages | https://build.nvidia.com/spark/openshell · https://build.nvidia.com/spark/nemoclaw |

## 2. The NemoClaw blueprint architecture (what judges grade you against)
NemoClaw = host-side orchestrator (the "plugin/CLI") that resolves a **versioned blueprint** and applies it through the **OpenShell** runtime.

- **A. Control / orchestration — "the Plugin (CLI)"** — TypeScript orchestrator on the host driving sandbox lifecycle. In-sandbox counterpart runs with OpenClaw, registering managed-inference metadata + runtime context prepended as system guidance. = your onboarding + lifecycle manager.
- **B. The Blueprint — "versioned YAML package"** — bundles the sandbox image, policy, inference profile, supporting assets. Python manifest/orchestrator (`blueprint.yaml`) + baseline policy (`openclaw-sandbox.yaml`). Four-stage lifecycle: `resolve artifact → verify digest → plan resources → apply via OpenShell CLI`.
- **C. OpenShell Gateway — "security runtime & gateway"** — owns sandbox lifecycle, networking, policy enforcement, credential custody, API/inference proxying. Every network call / filesystem access / model request is intercepted here.
- **D. The Sandbox — agent runtime** — the actual agent (OpenClaw / Hermes / Deep Agents) runs unmodified. Filesystem writable only under `/sandbox` and `/tmp`; everything else read-only.
- **E. Inference layer — "privacy router"** — routes model calls to NVIDIA NIM / Nemotron (cloud) or local Ollama/vLLM, **based on your policy, not the agent's preference.**
- **F. Integrations & State** — credentials, logs, workspace files, transcripts — held by host/gateway, never exposed raw to the agent.

**Four enforcement tiers (the security spine):**
| Tier | What it does | Mutability |
|---|---|---|
| Filesystem | read-only system paths; `/sandbox` + `/tmp` writable | **Static** — locked at creation (Landlock LSM + seccomp-BPF) |
| Process | blocks privilege escalation / dangerous syscalls; no root | **Static** — locked at creation |
| Network | endpoint + binary egress allowlist (L3–L7) | **Dynamic** — hot-reloadable |
| Inference | reroutes model calls to controlled backends | **Dynamic** — hot-reloadable |

**"Map your agent onto the blueprint" (the rubric):** state your harness (adapter layer), then walk each of the four tiers and say concretely what your agent touches — filesystem paths it writes, exact egress endpoints/binaries, that it runs non-root, how inference is pinned to a routed backend.

## 3. The real OpenShell policy YAML schema
```yaml
version: 1
filesystem_policy: { include_workdir, read_only[], read_write[] }   # STATIC
landlock:          { compatibility: best_effort | hard_requirement } # STATIC
process:           { run_as_user, run_as_group }                     # STATIC (never root/0)
network_policies:  { <name>: { name, endpoints[], binaries[] } }     # DYNAMIC
network_middlewares: { ... }                                          # DYNAMIC
```
Each network endpoint supports: `host`, `port`, `path`, `protocol` (`rest | websocket | graphql | mcp | json-rpc`), `tls: skip`, **`enforcement: enforce | audit`**, `access` (`read-only | read-write | full`), `rules: [ {allow: …} ]`, `deny_rules: [ … ]`, `allowed_ips: []`. Each policy lists the **`binaries`** allowed to use those endpoints (e.g. only `/usr/bin/gh` may hit `api.github.com`).

**Two ways the schema expresses a soft boundary:**
- `enforcement: enforce` → anything not matched by an `allow` rule is **denied** (structured `403` with `agent_guidance` + `next_steps`). Trigger for escalation.
- `enforcement: audit` → **logs violations but lets traffic through** ("observe, don't block" discovery mode). Audit *allows*, so it is not itself an approval gate. (Open feature request #1839 = audit2allow-style policy-learning.)

## 4. Human-in-the-loop / allow-with-escalation (Policy Advisor)
The real answer to "not just a blunt block" — a **flow, not a YAML key**:
1. Agent hits a denied endpoint → `403` with `agent_guidance`/`next_steps`.
2. Agent reads skill at `/etc/openshell/skills/policy_advisor.md`, inspects `GET /v1/policy/current` and `GET /v1/denials?last=10`.
3. Agent submits a **narrow proposal** (`POST /v1/proposals`, an `addRule` op) via in-sandbox `policy.local`.
4. **Human, from outside the sandbox**, decides:
   ```bash
   openshell rule get <sandbox> --status pending
   openshell rule approve <sandbox> --chunk-id <id>
   openshell rule reject  <sandbox> --chunk-id <id> --reason "Scope to docs/ only."
   ```
5. Agent polls `GET /v1/proposals/{chunk_id}/wait?timeout=300`. Approve → `policy_reloaded: true`, hot-reload, retry. Reject → `rejection_reason` + `validation_result` (e.g. `credential_reach_expansion`, `link_local_reach`) to refine.

Net: **default-deny posture, but denials become human-approvable proposals** — allow-with-escalation, not a dead end. Auto-approval off unless explicitly enabled.

## 5. Sample OpenShell policy — allow-with-escalation / HITL (schema-accurate)
Three-tier boundary: auto-allow reversible → hard-deny irreversible → everything else falls through default-deny into the Policy Advisor human loop.
```yaml
version: 1

# ---------- STATIC (locked at creation; recreate to change) ----------
filesystem_policy:
  include_workdir: true
  read_only:  [ /usr, /etc, /bin, /lib ]
  read_write: [ /sandbox, /tmp ]        # agent workspace only
landlock:
  compatibility: best_effort            # or hard_requirement to fail-closed on old kernels
process:
  run_as_user:  agent                   # never root / 0
  run_as_group: agent

# ---------- DYNAMIC (hot-reload via `openshell policy set <name> --policy f.yaml --wait`) ----------
network_policies:
  github_repos:
    name: github_repos
    endpoints:
      - host: api.github.com
        port: 443
        path: "/**"
        protocol: rest
        enforcement: enforce            # unmatched requests => default-DENY => escalates to Policy Advisor
        rules:
          - allow: { method: GET,  path: "/**" }          # Tier 1 reversible: auto
          - allow: { method: HEAD, path: "/**" }
          - allow: { method: POST,  path: "/repos/<org>/agent-scratch/issues" }   # scoped write
          - allow: { method: PATCH, path: "/repos/<org>/agent-scratch/issues/*" }
      - host: api.github.com
        port: 443
        path: "/graphql"
        protocol: graphql
        enforcement: enforce
        rules:
          - allow: { operation_type: query }
          - allow: { operation_type: mutation, fields: [createIssue, updateIssue, addComment] }
        deny_rules:
          - { operation_type: mutation, fields: [deleteRepository, deleteRef, updateBranchProtectionRule] }  # Tier 3 irreversible: HARD-deny
    binaries:
      - { path: /usr/bin/gh }           # only these binaries may use the endpoints above
      - { path: /usr/local/bin/claude }

  inference_gateway:                    # inference is just another egress rule
    name: inference_gateway
    endpoints:
      - host: inference.local           # host-side router picks NIM/Nemotron or local Ollama per operator policy
        port: 443
        protocol: rest
        enforcement: enforce
    binaries:
      - { path: /usr/local/bin/openclaw }
```
**Escalation tier in plain terms:** a `git push` to a *new*, non-allowlisted repo matches no `allow` → `enforce` returns `403` → agent submits an `addRule` proposal → `openshell rule approve/reject`. Approve → hot-reload → push proceeds. That's HITL on an irreversible-ish action, distinct from flat `deny_rules` reserved for the truly-never (repo deletion, branch-protection).

*Discovery tip:* set `enforcement: audit` on a new endpoint first to watch what the agent tries without blocking, capture the real egress set, then flip to `enforce`.

## 6. NemoClaw CLI
```bash
curl -fsSL https://www.nvidia.com/nemoclaw.sh | bash
nemoclaw onboard                       # interactive setup wizard (creates a named assistant/sandbox)
nemoclaw list
nemoclaw <name> status
nemoclaw <name> connect                # shell into the sandbox
nemoclaw <name> logs --follow
nemoclaw start | nemoclaw stop
nemoclaw <name> policy-add

# inside the sandbox
openclaw tui
openclaw agent --agent main --local -m "hello" --session-id test

# OpenShell primitives NemoClaw sits on
openshell sandbox create --policy ./my-policy.yaml -- claude
openshell policy set  <name> --policy current.yaml --wait      # replace full policy (hot-reload)
openshell policy update <name> --add-endpoint <SPEC> --wait     # incremental merge
openshell rule get/approve/reject <name> ...                   # Policy Advisor HITL approvals
openshell logs <name> --tail --source sandbox                  # watch denials
openshell term                                                 # live TUI dashboard
```

## 7. How inference gets routed
- Sandbox never talks to a provider directly — it addresses **`inference.local`**, intercepted by the **OpenShell gateway**. Provider creds live on the **host**, never in the sandbox.
- **Default (cloud):** NVIDIA NIM cloud API, `nvidia/nemotron-3-super-120b-a12b` ("Nemotron 3 Super 120B," agent-optimized).
- **Local / offline (experimental):** Ollama or vLLM on local GPU (DGX Spark path).
- **Model Router:** "chooses from the configured NVIDIA model pool per request."
- Routing is a **dynamic** section — hot-reloadable, no restart. Destination chosen **by your policy, not the agent's preference** — the agent can't exfiltrate to an arbitrary model endpoint. **← This is Airtight's core design invariant.**

## 8. Closest real bedrock primitives (grounding + fallback)
Even though the exact names resolve, OpenShell is built on:
- **Filesystem/process isolation:** Linux **Landlock LSM** + **seccomp-BPF** + namespaces — same primitives under gVisor / Firecracker / Kata microVMs.
- **L7 network policy w/ allow/deny + approval:** conceptually **OPA/Rego** / Kubernetes NetworkPolicy / Cilium, applied per-binary to agent egress.
- **NVIDIA analogues:** NeMo Agent Toolkit (OpenShell is described as part of it), NeMo Guardrails.
- **HITL pattern:** default-deny + propose-approve-reload mirrors audit2allow (SELinux) / PR approval gates.

**Fallback if the preview won't install on event hardware:** reproduce the same graded architecture with a gVisor/Firecracker sandbox + an OPA/Rego egress gate + a NeMo/NIM inference proxy + a manual approve step — and describe it in NemoClaw's four-tier vocabulary.

## Caveats
Early preview / not production-ready. File names `blueprint.yaml`, `openclaw-sandbox.yaml` are referenced conceptually in blogs but not pinned to exact paths in reference docs — verify against the actual repo on clone.

## Sources
NemoClaw repo/community/docs; NVIDIA Technical Blog build guide; OpenShell repo; OpenShell Policy Schema reference; Customize Sandbox Policies; Policy Advisor; default policy / community repo; security best practices; OpenShell issue #1839; dev.to & vietanh.dev write-ups; DeepWiki NVIDIA/OpenShell; OpenClaw repo. (Full URLs in §1 above.)
