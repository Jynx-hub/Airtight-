# containment/ — M5 policy + M6 adversarial demo

A faithful **simulation** of the OpenShell network tier and the Policy Advisor human-in-the-loop flow. OpenShell needs Linux (Landlock LSM + seccomp-BPF), so it can't run on macOS; on-site it stands up on hosted DGX Spark (`inference/policy/ONBOARDING.md`). This models the *decision logic* so the demo is rehearsable anywhere.

- `policy.py` — `decide(action, host, method, path)` parses the **real** `inference/policy/airtight-sandbox.yaml` and returns the three-tier gradient: ALLOW (reversible) / HARD_DENY (irreversible, matched deny_rule) / DEFAULT_DENY_ESCALATE (ambiguous → Policy Advisor). Decisions come from the file — editing a deny_rule flips the outcome.
- `openshell_sim.py` — prints the real CLI verbs + 403/proposal/reject flow (research §4/§6), every line tagged `[SIM]`.
- `demo.py` — `python -m containment.demo`: "file now + back up to Dropbox" → filing hard-denied, Dropbox default-denied → proposal rejected, vault read allowed. Fuses M5 (policy) and M2 (HiddenLayer on the tool_call hop via `guarded_tool`) on one egress action.

The shipped YAML runs `enforcement: audit` (observe, don't block); the sim uses `enforcement_override="enforce"` to model the judged run per the RUNBOOK's audit→enforce flip, and says so in a banner.
