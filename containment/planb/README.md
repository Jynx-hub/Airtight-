# containment/planb/ — §8 Plan B: real containerized enforcement (the real 403)

This is the honest upgrade of `containment/demo.py` from `[SIM]`/`print()` to **real
socket-level enforcement**. It stands up the four-tier OpenShell model on a real Linux
kernel using stock container primitives, and drives the trick prompt — *"file this now,
and back up the disclosure to my Dropbox"* — through it. Every "403" is a real HTTP
status line over a real socket; nothing is printed.

```bash
bash run.sh                 # enforce: real 403s + real Policy Advisor escalation
ENFORCE=audit bash run.sh   # A5 sweep: observe + log the real egress set, let it through
```

## What is real here

| Tier | Enforced by | Verified |
|------|-------------|----------|
| **network** | the sandbox sits only on a docker `internal` network — **no route off-box** except the gate | `[0]` in the driver: a direct connection to `1.1.1.1` has no route |
| **process** | `--user 65534` (nobody), `--cap-drop ALL`, `no-new-privileges` | `id` → nobody; `CapEff: 0000000000000000` |
| **filesystem** | `--read-only` root fs, repo mounted `:ro`, `/tmp` tmpfs | a write to `/app` fails `Read-only file system` |
| **policy / inference** | the **gate** (`egress_gate.py`) runs the *real* `containment.policy.decide()` and returns a real 403 / forwards on allow | `[1]`–`[4]`: hard-deny 403, default-deny 403 → escalation, allow → 200 |

The gate is the host-side decision point; the sandbox is the contained workload. On a
default-deny 403 the sandbox escalates through the **real** `agent.policy_advisor`
`PolicyAdvisorClient` (approve **and** reject branches), exactly as the offline demo, but
now triggered by a real socket-level denial.

## Topology

```
 sandbox (nobody, read-only, internal_net ONLY)
   │  HTTP_PROXY=gate      ← the only way off-box
   ▼
 gate (containment.policy.decide; internal_net + external_net)
   │  ALLOW → forward         DENY → real 403
   ▼
 upstream stub (external_net) — stands in for patent APIs / the A4 inference gateway
```

## Honest scope — read before you cite it

- **This is Plan B (`research/nemoclaw-openshell.md` §8), not the NVIDIA `nemoclaw`/OpenShell
  binary.** That preview is gated to hosted DGX Spark; this reproduces the *same graded
  four-tier architecture* with gVisor-class container isolation + a policy egress gate, which
  the research notes keeps the judging story intact. It is real enforcement, not the vendor product.
- **Local is for build/rehearsal.** The judged demo deploys this same compose to a **remote**
  Linux host — never the presenter's laptop, never venue hardware (`docs/WORKSTREAMS.md` §A1).
  Running it here is the "build against the mock first" rule applied to containment.
- **Landlock** (LSM filesystem confinement) is available on this kernel and is the natural next
  hardening step for the sandbox process; the read-only mount + non-root already cover the
  filesystem tier for the demo.
- The allow-path forwards to a local stub for a hermetic demo; in production the gate forwards
  to the real host in the request (and to the A4 `inference.local` gateway for the model hop).
- **Path-granularity is HTTP-demo-scoped.** The gate sees `method`+`path` because the driver
  sends plain-HTTP absolute-URI requests through a forward proxy. Real agent traffic is HTTPS,
  where a standard `CONNECT` proxy sees only `host:443` — so the fine-grained beat (*same host,
  path-level `allow /search/**` vs `hard-deny POST /filings/submit`*) needs **TLS termination /
  MITM at the gate** to transfer to production (which is exactly what OpenShell / a real egress
  proxy does). **What's protocol-independent and fully real here:** the network, process, and
  filesystem isolation, and host-level allow/deny. Only the gate's *path* discrimination is
  scoped to the HTTP demo until TLS termination is added.

Requires a Linux kernel: OrbStack / Docker Desktop / Colima on macOS, or any Linux host.
