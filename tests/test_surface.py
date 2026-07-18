"""Applicant Surface API tests — stub mode, no network.

Skipped if fastapi isn't installed, so a `.[dev]`-only clone stays green;
install with `.[web]` to exercise them.

The disk-reader tests build their own fixture trees under tmp_path rather than
reading `results/`. That directory is gitignored, so asserting against it would
pass here and fail on a fresh clone — and the states worth testing (a run killed
mid-flight, an older fingerprint schema) are exactly the ones you cannot rely on
being present.
"""

import json
import time

import pytest

pytest.importorskip("fastapi")

from fastapi.testclient import TestClient  # noqa: E402

from airtight import config  # noqa: E402
from airtight import guardrails as g  # noqa: E402
from surface import sources  # noqa: E402
from surface.app import app  # noqa: E402

client = TestClient(app)


@pytest.fixture(autouse=True)
def force_stub(monkeypatch, tmp_path):
    monkeypatch.setattr(config, "MODE", "stub")
    g.AUDIT_LOG.clear()  # module global — other test files leave entries in it
    # Keep test writes out of results/security/*.jsonl. Without this the suite
    # appends to the same log the admin frame reads, which is how 77 synthetic
    # "blocks" ended up looking like real agent activity.
    monkeypatch.setattr(g, "_SECURITY_DIR", tmp_path / "security")


def poll_job(job_id, timeout_s=10.0):
    deadline = time.monotonic() + timeout_s
    while time.monotonic() < deadline:
        snap = client.get(f"/api/draft/{job_id}").json()
        if snap["status"] in ("done", "error"):
            return snap
        time.sleep(0.02)
    raise AssertionError(f"job {job_id} did not finish within {timeout_s}s")


def hl_pii(monkeypatch):
    """Turn the bus on with a canned response that flags PII on every hop.

    MODEL_RESPONSE policy maps pii -> REDACT, so each model turn yields exactly
    one non-pass finding — which makes findings countable per request.
    """
    monkeypatch.setattr(config, "HL_ENABLED", True)
    monkeypatch.setattr(g, "_raw_analyze", lambda text, phase: {
        "metadata": {"event_id": "evt-test"},
        "analysis": [{"name": "pii", "phase": phase, "detected": True,
                      "findings": {"matches": []}}],
    })


def test_health_reports_mode():
    body = client.get("/api/health").json()
    assert body["mode"] == "stub" and body["model"]


def test_sample_is_a_valid_disclosure():
    body = client.get("/api/sample").json()
    assert body["id"] and body["technology_class"] and body["details"]


def test_index_serves_html():
    res = client.get("/")
    assert res.status_code == 200 and "Airtight" in res.text


def test_draft_returns_draft_and_report():
    disclosure = client.get("/api/sample").json()
    res = client.post("/api/draft", json=disclosure)
    assert res.status_code == 200
    body = res.json()
    assert body["draft"]["disclosure_id"] == disclosure["id"]
    assert len(body["draft"]["claims"]) >= 2
    # report exists; security scanning off in stub mode (honest, not faked)
    assert body["report"]["security_scanning"] is False
    assert body["report"]["security_findings"] == []
    assert "smart_catches" in body["report"]


def test_admin_page_serves():
    res = client.get("/admin")
    assert res.status_code == 200 and "ENGINE" in res.text


def test_static_assets_are_mounted():
    # `/` and `/admin` hand-serve HTML, but split CSS/JS needs the mount.
    for asset in ("/static/airtight.css", "/static/intake.js", "/static/admin.js"):
        assert client.get(asset).status_code == 200, asset


# ---------------------------------------------------------------------------
# Retrieval reaches the drafting turn
# ---------------------------------------------------------------------------

def test_draft_applies_retrieved_memory():
    """The regression this UI work exists to fix.

    `draft_patent(disclosure)` with no guardrails renders "(none on record)" and
    returns an empty `loopholes_closed` — i.e. the synchronous route silently ran
    the ablation's *control* arm and reported it as the product. This asserts the
    warmed arm is what ships.
    """
    disclosure = client.get("/api/sample").json()
    body = client.post("/api/draft", json=disclosure).json()
    assert body["report"]["loopholes_closed"], "drafting ran against an empty memory"
    assert body["draft"]["loopholes_closed"] == body["report"]["loopholes_closed"]


def test_audit_log_does_not_bleed_between_requests(monkeypatch):
    """Each report covers its own request only.

    g.AUDIT_LOG is a process global that is never cleared, so reading all of it
    after a draft re-attributes every earlier request's findings to this one.
    """
    hl_pii(monkeypatch)
    disclosure = client.get("/api/sample").json()

    first = client.post("/api/draft", json=disclosure).json()["report"]["security_findings"]
    second = client.post("/api/draft", json=disclosure).json()["report"]["security_findings"]

    assert first, "expected redact findings with the bus on"
    assert len(second) == len(first), (
        f"second request reported {len(second)} findings vs {len(first)} — audit log bled"
    )


# ---------------------------------------------------------------------------
# Job lifecycle
# ---------------------------------------------------------------------------

def test_job_runs_to_completion_with_stages():
    disclosure = client.get("/api/sample").json()
    started = client.post("/api/draft/start", json=disclosure).json()
    snap = poll_job(started["job_id"])

    assert snap["status"] == "done", snap["error"]
    assert snap["draft"]["disclosure_id"] == disclosure["id"]
    # The loop's real turns, read off the transcript draft_patent appends to.
    turns = [s["turn"] for s in snap["stages"]]
    assert turns[:3] == ["plan", "draft", "critique"]
    assert all(s["state"] == "done" for s in snap["stages"])
    assert snap["retrieval"]["selected"], "job did not retrieve before drafting"


def test_job_status_404_for_unknown_id():
    assert client.get("/api/draft/nosuchjob").status_code == 404


# ---------------------------------------------------------------------------
# Memory + retrieval explain
# ---------------------------------------------------------------------------

def test_memory_stats_reports_corpus_and_seams():
    body = client.get("/api/memory/stats").json()
    assert body["corpus"]["count"] > 0
    assert body["corpus"]["by_statute"], "statute is derived at validation — did a raw json.load slip in?"
    # Episodes/ingested are empty in a clean tree; each must say so and name its source.
    for key in ("episodes", "ingested"):
        if body[key]["count"] == 0:
            assert body[key]["seam"]["source"], f"{key} empty with no seam source"


def test_memory_records_filter_by_statute():
    body = client.get("/api/memory/records?statute=112&limit=5").json()
    assert body["total"] > 0
    assert all(r["statute"] == "112" for r in body["records"])


def test_retrieve_explains_exactly_what_the_store_returns():
    """The panel must show the retrieval that actually happens, not a re-implementation."""
    from airtight import Disclosure
    from surface import jobs

    disclosure = Disclosure.model_validate(client.get("/api/sample").json())
    records, payload = jobs.retrieve_for(disclosure, k=5)

    assert [r.id for r in records] == [r["id"] for r in payload["selected"]]
    assert payload["diversified"], "sample should span more than one statute"
    # Diversification is only visible if some higher-ranked record was passed over.
    assert payload["runners_up"]


def test_disclosures_list_is_summary_only():
    body = client.get("/api/disclosures").json()
    if not body.get("disclosures"):
        pytest.skip("no pulled disclosures in this clone")
    assert body["total"] > 0
    # `details` is the full claim listing and runs past 10 KB — never in a list.
    assert "details" not in body["disclosures"][0]


# ---------------------------------------------------------------------------
# Tolerant disk readers
# ---------------------------------------------------------------------------

def test_ablation_tolerates_incomplete_and_older_runs(monkeypatch, tmp_path):
    """Three real states: complete, killed mid-run, and a pre-revise fingerprint."""
    root = tmp_path / "ablation"
    complete = root / "20260718-122807"
    (complete / "transcripts").mkdir(parents=True)
    (complete / "results.json").write_text(json.dumps({
        "fingerprint": {"mode": "live", "k": 5, "revise_rounds": 1,
                        "prompt_sha256": {"REVISE_SYSTEM": "abc"}},
        "corpus_size": 17,
        "disclosures_completed": 1,
        "results": [
            {"disclosure_id": "d1", "condition": "empty", "loopholes_caught": 1,
             "checklist_size": 6, "drafting_seconds": 10.0, "defect_count": 2},
            {"disclosure_id": "d1", "condition": "warmed", "loopholes_caught": 4,
             "checklist_size": 6, "drafting_seconds": 9.0, "defect_count": 1},
        ],
        "pairs": [{"disclosure_id": "d1", "loopholes_caught_delta": 3}],
    }))
    # Killed mid-run: transcripts, no results.json. A naive reader 500s here.
    killed = root / "20260718-100851" / "transcripts"
    killed.mkdir(parents=True)
    (killed / "run0-d1-empty.json").write_text("{}")
    # Older schema: no revise_rounds, no split, no REVISE_SYSTEM hash.
    older = root / "20260718-042609"
    older.mkdir(parents=True)
    (older / "results.json").write_text(json.dumps(
        {"fingerprint": {"mode": "live", "prompt_sha256": {}}, "results": [], "pairs": []}))

    monkeypatch.setattr(sources, "ABLATION_DIR", root)
    out = sources.ablation_runs()

    by_id = {r["id"]: r for r in out["runs"]}
    assert by_id["20260718-100851"]["complete"] is False
    assert by_id["20260718-100851"]["seam"]["source"].endswith("20260718-100851/")
    assert by_id["20260718-042609"]["fingerprint"]["revise_rounds"] is None
    assert by_id["20260718-042609"]["fingerprint"]["has_revise_prompt"] is False
    # Newest complete run wins, and the caveat travels with the numbers.
    assert out["selected"]["id"] == "20260718-122807"
    assert out["selected"]["totals"]["warmed"]["caught"] == 4
    assert out["caveat"]["label"] == "SUPERSEDED RUN"


def test_ablation_without_any_runs_is_a_seam(monkeypatch, tmp_path):
    monkeypatch.setattr(sources, "ABLATION_DIR", tmp_path / "nope")
    out = sources.ablation_runs()
    assert out["runs"] == [] and out["selected"] is None and out["seam"]["source"]


def test_security_separates_live_events_from_fixtures(monkeypatch, tmp_path):
    """A real AIDR event_id is a UUID; pytest and the ingest rehearsal write neither."""
    d = tmp_path / "security"
    d.mkdir()
    (d / "audit.jsonl").write_text("\n".join(json.dumps(r) for r in [
        {"ts": "2026-07-18T12:00:00", "hop": "tool_call", "action": "block",
         "event_id": "e", "categories": []},
        {"ts": "2026-07-18T12:00:01", "hop": "ingested_document", "action": "quarantine",
         "event_id": "fake-rehearsal-0001", "categories": ["prompt_injection"]},
        {"ts": "2026-07-18T12:00:02", "hop": "model_response", "action": "pass",
         "event_id": "0fc717c2-6c54-4b01-90e6-d701748f0851", "categories": []},
    ]) + "\n")
    monkeypatch.setattr(sources, "SECURITY_DIR", d)

    out = sources.security_events()
    assert out["counts"] == {**out["counts"], "audit": 3, "live": 1, "synthetic": 2}
    assert out["sample_live_event_id"].startswith("0fc717c2")
    assert out["provenance_seam"]["label"] == "MIXED PROVENANCE"
    # The census matrix keeps every hop, including ones with no traffic.
    assert set(out["matrix"]) == set(sources.HOPS)
    assert out["matrix_live"]["model_response"]["pass"] == 1
    assert out["matrix_live"]["tool_call"]["block"] == 0


def test_security_tolerates_a_torn_line(monkeypatch, tmp_path):
    d = tmp_path / "security"
    d.mkdir()
    (d / "audit.jsonl").write_text(
        '{"hop": "user_prompt", "action": "pass", "event_id": "e"}\n{"hop": "tool_c'
    )
    monkeypatch.setattr(sources, "SECURITY_DIR", d)
    assert sources.security_events()["counts"]["audit"] == 1


def test_throughput_defaults_to_a_run_that_kneed(monkeypatch, tmp_path):
    """THROUGHPUT.md: the knee claim is an A100 result. A profile with no knee
    must never become the default view."""
    d = tmp_path / "bench"
    d.mkdir()
    levels = [{"concurrency": 1, "aggregate_tok_s": 90.0},
              {"concurrency": 16, "aggregate_tok_s": 800.0}]
    (d / "sweep-20260718T065759Z.json").write_text(json.dumps({
        "provenance": {"gpu_reported_by_operator": "L40S"}, "levels": levels,
        "summary": {"knee_concurrency": None, "headline_speedup_x": 9.42}}))
    (d / "sweep-20260718T055914Z.json").write_text(json.dumps({
        "provenance": {"gpu_reported_by_operator": "A100"}, "levels": levels,
        "summary": {"knee_concurrency": 16, "headline_speedup_x": 10.67}}))
    monkeypatch.setattr(sources, "BENCH_DIR", d)

    out = sources.throughput_sweeps()
    assert out["selected"]["summary"]["headline_speedup_x"] == 10.67
    assert out["selected"]["has_knee"] is True
    assert {s["id"] for s in out["sweeps"]} == {
        "sweep-20260718T065759Z", "sweep-20260718T055914Z"}


def test_concurrent_drafts_do_not_cross_attribute_findings(monkeypatch):
    """The offset slice is only a correct attribution if nothing interleaves.

    Sequential requests were fixed by the offset; overlapping ones were not —
    two worker threads append to g.AUDIT_LOG interleaved, so A's report picked up
    B's blocks. Drafts are now serialized process-wide.
    """
    import concurrent.futures

    hl_pii(monkeypatch)
    disclosure = client.get("/api/sample").json()

    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as pool:
        reports = [f.result()["report"]["security_findings"] for f in [
            pool.submit(lambda: client.post("/api/draft", json=disclosure).json())
            for _ in range(4)
        ]]

    counts = [len(r) for r in reports]
    assert all(c == counts[0] for c in counts), (
        f"concurrent drafts reported differing finding counts {counts} — audit log interleaved"
    )
    assert counts[0] > 0


def test_job_report_findings_are_captured_under_the_lock(monkeypatch):
    hl_pii(monkeypatch)
    disclosure = client.get("/api/sample").json()
    a = poll_job(client.post("/api/draft/start", json=disclosure).json()["job_id"])
    b = poll_job(client.post("/api/draft/start", json=disclosure).json()["job_id"])
    assert a["report"]["security_findings"], "expected redact findings with the bus on"
    assert len(a["report"]["security_findings"]) == len(b["report"]["security_findings"])


def test_one_bad_record_does_not_empty_the_corpus(tmp_path):
    """An empty corpus fails silently — it drafts the control arm with no seam.

    LoopholeStore.load raises on the first bad record, so wrapping the whole
    call meant one truncated file zeroed the retrievable set.
    """
    d = tmp_path / "corpus"
    d.mkdir()
    (d / "good.json").write_text(json.dumps([{
        "id": "keep-me", "pattern": "§101 abstract idea", "claim_shape": "c",
        "technology_class": "G06F", "remedy": "r", "source": "s"}]))
    (d / "torn.json").write_text('{"id": "half-writt')
    (d / "invalid.json").write_text(json.dumps([{"id": "missing-fields"}]))

    store, skipped = sources._load_store(d)
    assert len(store) == 1 and store.records[0].id == "keep-me"
    assert {s["file"] for s in skipped} == {"torn.json", "invalid.json"}


def test_memory_stats_and_records_count_the_same_store():
    """Both panels resolve through corpus_store(); a mismatch makes the stat tile
    and the browser under it disagree, and hides a CPC class from the filter."""
    stats = client.get("/api/memory/stats").json()
    records = client.get("/api/memory/records?limit=1").json()
    assert stats["corpus"]["count"] == records["total"]
    # Every class present in the browsable set must be reachable from a facet.
    for cpc in stats["corpus"]["by_class"]:
        assert client.get(f"/api/memory/records?cpc={cpc}&limit=1").json()["total"] > 0


def test_readers_survive_null_and_wrong_typed_fields(monkeypatch, tmp_path):
    """`.get(k, {})` returns None when k is present-and-null — the shape a run
    killed between emitting a key and filling it leaves behind."""
    bench = tmp_path / "bench"
    bench.mkdir()
    (bench / "sweep-a.json").write_text(json.dumps(
        {"provenance": {}, "summary": None, "levels": []}))
    monkeypatch.setattr(sources, "BENCH_DIR", bench)
    out = sources.throughput_sweeps()
    assert out["selected"] is None and out["seam"]["label"] == "NO PLOTTABLE SWEEP"

    abl = tmp_path / "abl"
    (abl / "r1").mkdir(parents=True)
    (abl / "r1" / "results.json").write_text(json.dumps(["not", "a", "dict"]))
    monkeypatch.setattr(sources, "ABLATION_DIR", abl)
    assert sources.ablation_runs()["runs"][0]["complete"] is False

    sec = tmp_path / "sec"
    sec.mkdir()
    (sec / "audit.jsonl").write_text(json.dumps(
        {"ts": None, "hop": "tool_call", "action": "block", "categories": None}) + "\n")
    monkeypatch.setattr(sources, "SECURITY_DIR", sec)
    assert sources.security_events()["counts"]["audit"] == 1  # sorted() on a null ts


def test_containment_survives_malformed_yaml_and_partial_rules(monkeypatch, tmp_path):
    """yaml.YAMLError is not a ValueError, and this panel invites YAML edits."""
    broken = tmp_path / "broken.yaml"
    broken.write_text("network_policies:\n  a:\n   endpoints:\n  - bad: [")
    monkeypatch.setattr(sources, "POLICY_PATH", broken)
    out = sources.containment_policy()
    assert out["error"] and len(out["tiers"]) == 4  # degrades, never raises

    partial = tmp_path / "partial.yaml"
    partial.write_text(
        'network_policies:\n  f:\n    endpoints:\n      - host: h\n'
        '        deny_rules:\n          - {path: "/x"}\n')
    monkeypatch.setattr(sources, "POLICY_PATH", partial)
    assert sources.containment_policy()["endpoints"][0]["deny"] == ["ANY /x"]


def test_retrieval_explain_does_not_overclaim_diversification():
    """runners_up are the next records in rank order, not records that beat a
    pick — the panel used to assert the latter unconditionally."""
    from airtight import Disclosure
    from surface import jobs

    disclosure = Disclosure.model_validate(client.get("/api/sample").json())
    _, payload = jobs.retrieve_for(disclosure, k=5)

    claimed = payload["runners_up_outscored_a_pick"]
    worst_pick = min(r["score"] for r in payload["selected"])
    actually = any(u["score"] > worst_pick for u in payload["runners_up"])
    assert claimed is actually


def test_containment_exposes_tiers_and_the_hard_deny():
    body = client.get("/api/containment").json()
    assert body["error"] is None
    assert [t["tier"] for t in body["tiers"]] == [
        "filesystem", "process", "network", "inference"]
    # Two locked at creation, two hot-reloadable — the split is the point.
    assert [t["mutability"] for t in body["tiers"]].count("dynamic") == 2
    # The filing POST is the irreversible action that cannot be escalated.
    denies = [d for e in body["endpoints"] for d in e["deny"]]
    assert "POST /filings/submit" in denies
    assert body["enforcement_seam"]["label"] == "SIMULATED"
