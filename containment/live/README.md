# containment/live/ — the OpenShell policy gate, LIVE and online

Public deployment of the real `containment.policy` decision, running the real
`inference/policy/airtight-sandbox.yaml`. Every deny is a **real HTTP 403** over the
internet; the operator approve/reject is a real decision made by the caller (HITL).

**Live URL:** https://airtight-openshell.vercel.app
(Vercel, single Python entrypoint `index.py`. Deploy: `deploy_to_vercel` with `index.py` +
`pyproject.toml`.)

## API

`POST /api/gate` — egress decision. Body: `{ "host", "method", "path" }`
- **200** `{"decision":"allow", ...}` — matched an allow rule / read-only access.
- **403** `{"decision":"hard_deny", "reason", "matched_rule"}` — irreversible, not escalable.
- **403** `{"decision":"default_deny_escalate", "agent_guidance"}` — un-allowlisted egress.

`POST /api/gate` — operator decision on a default-deny. Body:
`{ "action":"escalate", "host", "method", "path", "approve": true|false }`
- **200** `{"chunk_id","status":"approved","rule":{...}}` — the operator added the rule.
- **200** `{"chunk_id","status":"rejected","rejection_reason","validation_result"}`.
- **409** if the action was a `hard_deny` (never escalable).

`GET /health` — `{ok, service, policies:[...]}`. `GET /` — a demo page (bonus; your UI can
ignore it and call `/api/gate` directly).

### Example
```bash
curl -sw '\n[%{http_code}]\n' -X POST https://airtight-openshell.vercel.app/api/gate \
  -H 'Content-Type: application/json' \
  -d '{"host":"api.dropboxapi.com","method":"POST","path":"/2/files/upload"}'
# -> {"decision":"default_deny_escalate", ...}  [403]
```

## Scope, honestly

This is the **policy / 403 / Policy-Advisor** tier, live. The kernel-isolation tiers
(no route off-box · non-root · read-only fs) run in `containment/planb/` on a Docker host —
serverless has no namespaces. Both are real; this is the online half. The decision logic here
is faithful to `containment/policy.py` (verified: same outcomes on the trick-prompt cases).
