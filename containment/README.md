# containment/ — M5 policy + M6 adversarial demo

A faithful **simulation** of the OpenShell network tier and the Policy Advisor human-in-the-loop flow. OpenShell needs Linux (Landlock LSM + seccomp-BPF), so it can't run on macOS; on-site it stands up on hosted DGX Spark (`inference/policy/ONBOARDING.md`). This models the *decision logic* so the demo is rehearsable anywhere.

- `policy.py` — `decide(action, host, method, path)` parses the **real** `inference/policy/airtight-sandbox.yaml` and returns the three-tier gradient: ALLOW (reversible) / HARD_DENY (irreversible, matched deny_rule) / DEFAULT_DENY_ESCALATE (ambiguous → Policy Advisor). Decisions come from the file — editing a deny_rule flips the outcome.
- `openshell_sim.py` — prints the real CLI verbs + 403 flow (research §4/§6), every line tagged `[SIM]`. `proposal()` renders the **real** `agent.policy_advisor.Proposal` object the escalation client returned (approve *or* reject) — not a hardcoded string.
- `demo.py` — `python -m containment.demo`, driven by `fixtures/exfil_request.json`: **[1]** filing → hard-denied, never escalated; **[2]** Dropbox → default-deny → real `PolicyAdvisorClient.escalate()` → operator **rejects**; **[3]** a legitimate un-allowlisted prior-art host → escalate → operator **approves** → retry proceeds (both branches demonstrable); **[4]** the fusion — the vault read is **allowed** by policy, yet HiddenLayer quarantines the disclosure bytes on the `TOOL_RESULT` hop. Two independent gates on one action (M5 policy + M2 guardrails), not a `guarded_tool` block stranded behind a deny.

Honest scope: the deny and the proposal are real (decision from the YAML, proposal from the injectable client), but the "403" is a `[SIM]` line — a socket-level refusal needs the enforcing OpenShell gateway (A1) and host-side creds (A4), which need Linux/DGX.

The shipped YAML runs `enforcement: audit` (observe, don't block); the sim uses `enforcement_override="enforce"` to model the judged run per the RUNBOOK's audit→enforce flip, and says so in a banner.
