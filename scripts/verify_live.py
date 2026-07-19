#!/usr/bin/env python3
"""Prove the six "smoke-tested live" claims, or say which one is not.

Exists because a handoff claimed 6/6 live and three of the six turned out to be
offline-only, stub-mode, or contradicted by the audit — with no way to check short of
re-deriving each one by hand. This is that check, in one command:

    .venv/bin/python scripts/verify_live.py            # all six
    .venv/bin/python scripts/verify_live.py --skip planb   # skip the slow docker build

Honesty rules this script enforces, because they are the ones that were violated:
  * A missing prerequisite reports **BLOCKED**, never PASS. 5 passing + 1 blocked
    prints "5/6", not "green".
  * The HiddenLayer check asserts the returned `event_id` is a real AIDR UUID. Every
    one of the 257 hops banked before 2026-07-19 was a fixture (`e`, `fake-*`,
    `hl-demo-001`), which is exactly how a stub run got reported as live.
  * The USPTO check asserts hits land in the disclosure's own CPC class. An earlier
    pass returned recent unclassified filings (display devices, biology) and still
    looked like a successful live call.
"""

from __future__ import annotations

import argparse
import json
import os
import pathlib
import re
import subprocess
import sys
import urllib.request

ROOT = pathlib.Path(__file__).resolve().parent.parent
UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.I)

PASS, BLOCKED, FAIL = "PASS", "BLOCKED", "FAIL"


def check_surface() -> tuple[str, list[str]]:
    """Every frame and read-side API route serves from the current tree."""
    import threading
    import time
    import uvicorn

    from surface.app import app

    port = 8899
    server = uvicorn.Server(uvicorn.Config(app, host="127.0.0.1", port=port, log_level="error"))
    thread = threading.Thread(target=server.run, daemon=True)
    thread.start()
    for _ in range(50):
        if server.started:
            break
        time.sleep(0.1)
    else:
        return FAIL, ["surface did not start within 5s"]

    routes = ["/", "/admin", "/api/health", "/api/ablation", "/api/security",
              "/api/containment", "/api/throughput", "/api/memory/stats"]
    out, bad = [], []
    try:
        for r in routes:
            try:
                with urllib.request.urlopen(f"http://127.0.0.1:{port}{r}", timeout=8) as resp:
                    code = resp.status
            except Exception as exc:
                code = f"ERR {type(exc).__name__}"
            out.append(f"{r:22s} {code}")
            if code != 200:
                bad.append(r)
    finally:
        server.should_exit = True
        thread.join(timeout=5)

    if bad:
        return FAIL, out + [f"non-200 routes: {bad}"]
    return PASS, out + [f"{len(routes)}/{len(routes)} routes 200 on the current tree"]


def check_planb() -> tuple[str, list[str]]:
    """Real socket-level enforcement on a Linux kernel: 403s, escalation, allowed 200."""
    if subprocess.run(["docker", "info"], capture_output=True).returncode != 0:
        return BLOCKED, ["docker daemon not running — start Docker Desktop / OrbStack"]

    proc = subprocess.run(["bash", "run.sh"], cwd=ROOT / "containment" / "planb",
                          capture_output=True, text=True, timeout=900)
    lines = [l for l in proc.stdout.splitlines() if "✔" in l or "PASS" in l or "FAIL" in l]
    if proc.returncode != 0:
        return FAIL, lines[-12:] or [proc.stdout[-500:]]
    # the driver's own assertions are the evidence; require the real-403 beats
    joined = "\n".join(lines)
    if "REAL 403" not in joined or "REAL 200" not in joined:
        return FAIL, lines + ["expected both a REAL 403 and a REAL 200 in the driver output"]
    return PASS, lines


def check_vercel() -> tuple[str, list[str]]:
    """The live containment gate answers over the public internet."""
    url = "https://airtight-openshell.vercel.app/api/gate"
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            body = json.loads(resp.read())
            code = resp.status
    except Exception as exc:
        return FAIL, [f"{url} -> {type(exc).__name__}: {exc}"]
    if code != 200 or not body.get("ok"):
        return FAIL, [f"HTTP {code}", json.dumps(body)[:300]]
    return PASS, [f"HTTP 200 {url}", f"policies: {body.get('policies')}"]


def check_hiddenlayer() -> tuple[str, list[str]]:
    """A real AIDR call on a real hop, proven by a real event_id UUID."""
    from airtight import config

    if not (config.HL_CLIENT_ID and config.HL_CLIENT_SECRET) and not config.HL_TOKEN:
        return BLOCKED, [
            "no HiddenLayer credentials in .env",
            "need HIDDENLAYER_CLIENT_ID + HIDDENLAYER_CLIENT_SECRET, or HIDDENLAYER_TOKEN",
            "event key expires every 24h — event code AITX-2026, HIDDENLAYER_ENVIRONMENT=prod-us",
            "then re-run with AIRTIGHT_HL_ENABLED=true",
        ]
    if not config.HL_ENABLED:
        return BLOCKED, ["credentials present but AIRTIGHT_HL_ENABLED is false — analyze() "
                         "short-circuits to PASS and nothing reaches AIDR"]

    from airtight import guardrails as g

    poisoned = (ROOT / "data" / "fixtures" / "poisoned_prior_art.txt").read_text()
    verdict = g.analyze(g.Hop.TOOL_RESULT, poisoned, source="verify_live")
    eid = verdict.event_id or ""
    out = [f"hop=tool_result action={verdict.action.value} event_id={eid or '(none)'}",
           f"categories: {[d.category for d in verdict.detections if d.detected]}"]
    if not UUID_RE.match(str(eid)):
        return FAIL, out + [
            f"event_id {eid!r} is not a real AIDR UUID — this is a fixture/stub response, "
            "which is exactly the failure mode that got reported as 'live' before"]
    return PASS, out + ["event_id is a real AIDR UUID"]


def check_gateway() -> tuple[str, list[str]]:
    """inference.local gateway injects creds host-side; the sandbox holds none."""
    proc = subprocess.run([sys.executable, "runtime/gateway_smoke.py"], cwd=ROOT,
                          capture_output=True, text=True, timeout=180)
    lines = [l for l in proc.stdout.splitlines() if l.strip()]
    if proc.returncode != 0:
        return FAIL, lines[-10:] or [proc.stderr[-400:]]
    return PASS, lines[-7:] + ["(provider is the local mock — proves the credential "
                               "boundary, not a live GPU round-trip)"]


def check_uspto() -> tuple[str, list[str]]:
    """Live USPTO ODP prior-art search returning in-domain results."""
    from airtight import Disclosure, config
    from agent.prior_art import search_prior_art

    if not os.getenv("USPTO_API_KEY"):
        return BLOCKED, ["USPTO_API_KEY not set in the environment/.env"]

    fixture = ROOT / "data" / "fixtures" / "sample_disclosure.json"
    d = Disclosure.model_validate_json(fixture.read_text())
    cpc = (d.technology_class or "").strip()

    # The product path, through the guarded tool and the whole bus.
    recs = search_prior_art(d, limit=5)
    out = [f"disclosure {d.id} CPC={cpc} -> {len(recs)} live hits"]
    if not recs:
        return FAIL, out + ["zero hits — a live key returning nothing is not a passing check"]

    # Domain check reads the RECORD's own cpcClassificationBag, via the raw fetch.
    # Do NOT check LoopholeRecord.technology_class: `_to_loophole` copies that field
    # off the disclosure, so comparing the two is self-referential and cannot fail —
    # it reported "all 5 hits in-domain" for a result set that included a G06Q/H04L
    # primary. A check that cannot fail is worse than no check: it reads as evidence.
    from agent.prior_art import _fetch, _query

    raw = _fetch(_query(d), cpc, 5)
    tagged, primary = [], []
    for r in raw:
        bag = ((r.get("applicationMetaData") or {}).get("cpcClassificationBag")) or []
        num = r.get("applicationNumberText")
        classes = [c.split()[0] for c in bag if c.split()]
        out.append(f"  {num} cpc={classes[:4]}")
        if any(c.startswith(cpc) for c in classes):
            tagged.append(num)
        if classes and classes[0].startswith(cpc):
            primary.append(num)

    off = [r.get("applicationNumberText") for r in raw
           if r.get("applicationNumberText") not in tagged]
    if off:
        return FAIL, out + [f"{off} carry no {cpc} class at all — the CPC filter is not applied"]
    return PASS, out + [
        f"{len(tagged)}/{len(raw)} carry a {cpc} class (what the query filters on); "
        f"{len(primary)}/{len(raw)} have it as the PRIMARY class — the query is "
        f"CPC-filtered, and relevance-weighted within that"]


CHECKS = [
    ("surface", "Surface — both frames + read-side APIs", check_surface),
    ("planb", "Plan B — real socket-level 403 on a Linux kernel", check_planb),
    ("vercel", "Vercel gate — live over the public internet", check_vercel),
    ("hiddenlayer", "HiddenLayer — real AIDR hop with a real event_id", check_hiddenlayer),
    ("gateway", "Gateway — creds injected host-side", check_gateway),
    ("uspto", "USPTO prior-art — live, CPC-scoped", check_uspto),
]

GLYPH = {PASS: "✔", BLOCKED: "▲", FAIL: "✘"}


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skip", nargs="*", default=[], metavar="NAME",
                    help=f"checks to skip: {', '.join(n for n, _, _ in CHECKS)}")
    args = ap.parse_args()

    results = []
    for name, title, fn in CHECKS:
        if name in args.skip:
            print(f"\n— {title}\n  (skipped)")
            continue
        print(f"\n— {title}")
        try:
            status, evidence = fn()
        except Exception as exc:
            status, evidence = FAIL, [f"{type(exc).__name__}: {exc}"]
        for line in evidence:
            print(f"    {line}")
        print(f"  {GLYPH[status]} {status}")
        results.append((name, status))

    passed = sum(1 for _, s in results if s == PASS)
    blocked = [n for n, s in results if s == BLOCKED]
    failed = [n for n, s in results if s == FAIL]

    print(f"\n{'=' * 62}\n{passed}/{len(results)} verified live")
    if blocked:
        print(f"BLOCKED (missing prerequisite, not a failure): {', '.join(blocked)}")
    if failed:
        print(f"FAILED: {', '.join(failed)}")
    if not blocked and not failed:
        print("All checks verified against live systems.")
    return 0 if passed == len(results) else 1


if __name__ == "__main__":
    sys.exit(main())
