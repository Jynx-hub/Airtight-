# Quarantined docs

Moved out of `docs/` on 2026-07-18 to keep the build-facing doc set minimal. Nothing here
is wrong so much as superseded or off-focus — kept because the reasoning is worth reading,
not because anything should be wired against it.

| File | Why it moved | What replaced it |
|---|---|---|
| `BUILD-PLAN.md` | Milestone framing (M1–M6) that the task board now carries directly. Its two durable decisions were folded forward: the cloud-only deployment rule → `docs/WORKSTREAMS.md` §A1, the self-assessment → `docs/JUDGING-RUBRIC.md` | `docs/WORKSTREAMS.md` |
| `SESSIONS.md` | Per-milestone Claude Code kickoff prompts written against the `src/` layout, which is itself quarantined under `attic/src/`. Following them now would scaffold into a dead tree | `docs/WORKSTREAMS.md` blocks A–D |
| `UI-DESIGN-BRIEF.md` | A paste-ready prompt for rebuilding `surface/static/index.html`. Still usable, but the surface lane is not the current focus — retrieve it if D3/D5 come back on the board | — |

The `attic/` convention: quarantined, not deleted. `git mv` back if a decision reverses.
See `attic/README.md` for the code that was quarantined and why.
