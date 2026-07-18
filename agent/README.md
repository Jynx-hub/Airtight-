# agent/ — Person 4's lane (Anudeep)

The robot: work loop, memory, guardrails, eval harness. Tasks G0-G5: `docs/WORKSTREAMS.md` · session scripts: `docs/SESSIONS.md`.

**The one rule:** import from `airtight` (the doorway + shapes). Never construct a model client anywhere else — `airtight/doorway.py` is the single hop that inference.local pins, HiddenLayer analyzes, and OpenShell contains.

- `loop.py` — plan → draft → self-critique (M1)
- `run_smoke.py` — end-to-end check; stub mode needs no network
- M2 (HiddenLayer), M3 (memory/RAG), M4 (eval harness) land here next
