#!/usr/bin/env bash
# §8 Plan B — stand up the real enforcement locally and drive the trick prompt through
# it. Requires a Linux kernel (OrbStack / Docker Desktop / any Linux host). This is the
# BUILD/REHEARSAL path; the judged demo deploys the same compose to a REMOTE Linux host
# (never local, never venue hardware — docs/WORKSTREAMS.md §A1).
set -euo pipefail
cd "$(dirname "$0")"

echo "▶ building the sandbox image…"
docker build -t airtight-planb -f Dockerfile . >/dev/null

echo "▶ standing up gate + upstream + sandbox (real 403 enforcement)…"
# --exit-code-from sandbox: the run's exit code IS the sandbox driver's assertions.
set +e
docker compose up --abort-on-container-exit --exit-code-from sandbox
code=$?
set -e

echo "▶ tearing down…"
docker compose down -v >/dev/null 2>&1 || true
exit $code
