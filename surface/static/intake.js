/* Intake frame — disclosure in, context matched, loop watched, patent out.
 *
 * Drafting goes through the job routes rather than the blocking POST: a live
 * draft is several sequential model turns and has been measured at 257s, and the
 * loop's stages are the most interesting thing to look at while it runs. */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};

const POLL_MS = 400;
let polling = null;

/* ---------------- status bar ---------------- */

async function health() {
  try {
    const h = await (await fetch("/api/health")).json();
    setLed("led-mode", "MODE", h.mode, h.mode === "live" ? "on" : "off");
    setLed("led-model", "MODEL", h.model.split("/").pop(), "on");
    setLed("led-hl", "HIDDENLAYER", h.hl_enabled ? "on" : "off", h.hl_enabled ? "on" : "off");
  } catch {
    setLed("led-mode", "MODE", "offline", "alert");
  }
}

function setLed(id, label, value, state) {
  const node = $(id);
  node.className = `led ${state}`;
  node.innerHTML = "";
  node.append(`${label} `, el("b", null, value));
}

/* ---------------- sample ---------------- */

async function loadSample() {
  const d = await (await fetch("/api/sample")).json();
  $("f-title").value = d.title;
  $("f-class").value = d.technology_class;
  $("f-inventors").value = d.inventors.join(", ");
  $("f-summary").value = d.summary;
  $("f-details").value = d.details;
  $("disc-meta").textContent = `sample · ${d.id}`;
  previewContext();
}

/* ---------------- live context preview ----------------
 * Retrieval is pure BM25 over the corpus — no model call, single-digit ms — so
 * it can run while the inventor types instead of waiting for submit. Watching
 * the matched failure modes change as the disclosure is described is the whole
 * "compares against what it knows" argument, made continuous. */

let previewTimer = null;

function schedulePreview() {
  clearTimeout(previewTimer);
  previewTimer = setTimeout(previewContext, 350);
}

async function previewContext() {
  const d = readForm();
  if (!d.title && !d.summary && !d.details) return;
  try {
    const res = await fetch("/api/memory/retrieve", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(d),
    });
    if (res.ok) renderRetrieval(await res.json(), true);
  } catch { /* preview is best-effort; the real retrieval runs with the job */ }
}

function readForm() {
  return {
    id: "ui-" + Date.now(),
    title: $("f-title").value,
    technology_class: $("f-class").value,
    inventors: $("f-inventors").value.split(",").map((s) => s.trim()).filter(Boolean),
    summary: $("f-summary").value,
    details: $("f-details").value,
  };
}

/* ---------------- context match ---------------- */

function renderRetrieval(r, isPreview) {
  const body = $("ctx-body");
  body.innerHTML = "";
  if (!r) {
    body.append(el("p", "empty", "Retrieving…"));
    return;
  }

  $("ctx-meta").textContent = `${r.selected.length} of ${r.corpus_size} records · k=${r.k}`
    + (isPreview ? " · live" : "");

  const head = el("div", "stats");
  head.style.marginBottom = ".8rem";
  head.append(
    stat(r.selected.length, "retrieved"),
    stat(r.statutes_covered.length, "statutes"),
    stat(r.corpus_size, "corpus", "muted"),
  );
  body.append(head);

  // Diversification is the claim; show whether it actually happened this time.
  const note = el("div", "note");
  note.textContent = r.diversified
    ? `Statute-diversified across §${r.statutes_covered.join(" · §")} — the round-robin takes one `
      + `record per statute before any statute gets a second, so a §103-heavy corpus can't crowd out §101.`
    : `Only §${r.statutes_covered.join("/")} matched — nothing to diversify across at k=${r.k}.`;
  body.append(note);

  if (r.self_retrieval_warning) {
    const warn = el("div", "note defect");
    warn.textContent = "Self-retrieval: at least one record was mined from this same application. "
      + "Expected when demoing with a corpus disclosure — it is the examiner's own rejections coming back.";
    body.append(warn);
  }

  const max = Math.max(...r.selected.map((s) => s.score), 1);
  for (const rec of r.selected) body.append(recordRow(rec, max));

  const foot = el("p", "small muted");
  foot.style.marginTop = ".8rem";
  foot.textContent = `Ranked by ${r.ranking.algorithm} · k1=${r.ranking.k1} b=${r.ranking.b}. `
    + `b deviates from the literature default 0.75 deliberately: measured, it cuts cross-disclosure `
    + `overlap from 0.104 to 0.098 and keeps self-noise out of the top 10.`;
  body.append(foot);
}

function stat(n, label, cls) {
  const s = el("div", "stat");
  s.append(el("div", `n ${cls || ""}`, String(n)), el("div", "l", label));
  return s;
}

function recordRow(rec, max) {
  const row = el("div");
  row.style.cssText = "padding:.55rem 0;border-top:1px solid var(--line)";

  const hd = el("div");
  hd.style.cssText = "display:flex;gap:.4rem;align-items:center;flex-wrap:wrap;margin-bottom:.3rem";
  hd.append(el("span", "tag accent", `§${rec.statute}`));
  if (rec.class_match) hd.append(el("span", "tag", `${rec.technology_class} match`));
  if (rec.confidence < 1) hd.append(el("span", "tag", `conf ${rec.confidence}`));
  if (rec.self_retrieval) hd.append(el("span", "tag defect", "self"));
  const rank = el("span", "small muted mono", `#${rec.rank} · ${rec.score}`);
  rank.style.marginLeft = "auto";
  hd.append(rank);
  row.append(hd);

  const bar = el("div", "meter");
  bar.style.gridTemplateColumns = "1fr";
  const track = el("div", "track");
  const fill = el("div", `fill ${rec.trusted ? "" : "deep"}`);
  fill.style.width = `${Math.max(3, (rec.score / max) * 100)}%`;
  track.append(fill);
  bar.append(track);
  row.append(bar);

  row.append(el("div", "small", rec.pattern));
  const terms = el("div", "small muted mono");
  terms.style.marginTop = ".2rem";
  terms.textContent = rec.terms.length ? `matched: ${rec.terms.join(" ")}` : "matched on class only";
  row.append(terms);
  return row;
}

/* ---------------- pipeline ---------------- */

function renderPipeline(snap) {
  const box = $("pipeline");
  box.innerHTML = "";
  $("pipe-meta").textContent = `${snap.status} · ${snap.elapsed_s}s`;

  if (snap.status === "retrieving") {
    box.append(el("p", "empty pulsing", "Matching the disclosure against memory…"));
    return;
  }

  for (const s of snap.stages) {
    const row = el("div");
    row.style.cssText = "border-top:1px solid var(--line);padding:.5rem 0";

    const hd = el("div");
    hd.style.cssText = "display:flex;gap:.5rem;align-items:center;flex-wrap:wrap";
    const dot = el("span", `led ${s.state === "done" ? "on" : s.state === "running" ? "on pulsing" : "off"}`);
    dot.append(el("b", null, s.label));
    hd.append(dot);
    hd.append(el("span", "small muted", s.detail));
    const state = el("span", "tag");
    state.textContent = s.state;
    state.style.marginLeft = "auto";
    hd.append(state);
    row.append(hd);

    if (s.reply) {
      const det = el("details");
      det.style.marginTop = ".35rem";
      const sum = el("summary", "small muted");
      sum.style.cursor = "pointer";
      sum.textContent = `${s.reply.length.toLocaleString()} chars`;
      const pre = el("pre", "small mono wrap", s.reply);
      pre.style.cssText = "color:var(--muted);margin:.4rem 0 0;max-height:220px;overflow:auto";
      det.append(sum, pre);
      row.append(det);
    }
    box.append(row);
  }
}

/* ---------------- grant ---------------- */

function renderGrant(snap) {
  const { draft, report } = snap;
  $("grant-panel").classList.remove("hidden");
  $("grant-meta").textContent = `${draft.claims.length} claims · ${snap.elapsed_s}s`;

  const claims = $("claims");
  claims.innerHTML = "";
  draft.claims.forEach((c, i) => {
    const row = el("div");
    row.style.cssText = "display:grid;grid-template-columns:2rem 1fr;gap:.5rem;padding:.5rem 0;border-top:1px solid var(--line)";
    const n = el("div", "mono", String(i + 1) + ".");
    n.style.color = "var(--accent)";
    row.append(n, el("div", "small", c));
    claims.append(row);
  });

  // D3 was a textarea that silently discarded every edit. A read-only claim plus
  // an honest note is worth more than a control that pretends.
  const seam = el("div", "seam inline");
  seam.style.marginTop = ".7rem";
  seam.append(
    el("span", "label", "Editing not wired"),
    el("div", "detail", "Claims are read-only. Steering them needs a route that accepts a modified Draft."),
    el("div", "src", "PATCH /api/draft/{job_id} · surface/app.py"),
  );
  claims.append(seam);

  const rep = $("report");
  rep.innerHTML = "";
  rep.append(section("Loopholes pre-empted from memory", report.loopholes_closed,
    "no records retrieved — memory is empty for this class"));
  rep.append(section("Smart catches · self-critique", report.smart_catches,
    "the examiner turn raised nothing"));

  // loopholes_closed is what the drafting turn was primed with, not a verified
  // cure. The judge that verifies closure lives in the eval harness and does not
  // run on this path — say so rather than implying a graded result.
  if (report.loopholes_closed.length) {
    const n = el("div", "note");
    n.textContent = `${report.guardrails_applied} recorded failure modes were put in front of the drafting `
      + `turn. Whether each is actually closed is graded by the eval harness (agent/eval/judge.py), `
      + `which does not run here.`;
    rep.append(n);
  }

  const sec = el("div");
  sec.style.marginTop = ".8rem";
  sec.append(el("h4", "mono small muted", "Runtime security"));
  if (!report.security_scanning) {
    const s = el("div", "seam inline");
    s.append(
      el("span", "label", "Scanning off"),
      el("div", "detail", "HiddenLayer is disabled, so no hop was analyzed. With it on, injections in "
        + "ingested prior art and exfil in tool calls surface here."),
      el("div", "src", "AIRTIGHT_HL_ENABLED=true"),
    );
    sec.append(s);
  } else if (!report.security_findings.length) {
    sec.append(el("p", "small muted", "All hops analyzed — nothing tripped."));
  } else {
    for (const f of report.security_findings) {
      const line = el("div", "small");
      line.style.padding = ".25rem 0";
      line.append(el("span", `tag ${f.action === "block" ? "defect" : "accent"}`, f.action));
      line.append(` ${f.hop}`);
      if (f.source) line.append(el("span", "muted", ` ${f.source}`));
      if (f.categories.length) line.append(el("span", "muted", ` — ${f.categories.join(", ")}`));
      sec.append(line);
    }
  }
  rep.append(sec);

  $("spec").textContent = draft.specification;
}

function section(title, items, empty) {
  const box = el("div");
  box.style.marginBottom = ".8rem";
  box.append(el("h4", "mono small muted", `${title} (${items.length})`));
  if (!items.length) {
    box.append(el("p", "empty", empty));
    return box;
  }
  const ul = el("ul", "small");
  ul.style.cssText = "margin:.3rem 0 0;padding-left:1.1rem;color:var(--muted)";
  for (const it of items) ul.append(el("li", null, it));
  box.append(ul);
  return box;
}

/* ---------------- run ---------------- */

async function draft() {
  clearInterval(polling);
  $("btn-draft").disabled = true;
  $("grant-panel").classList.add("hidden");
  $("status").textContent = "Starting…";
  renderRetrieval(null);

  try {
    const res = await fetch("/api/draft/start", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(readForm()),
    });
    if (!res.ok) throw new Error(await res.text());
    const { job_id } = await res.json();
    $("status").textContent = "";
    polling = setInterval(() => poll(job_id), POLL_MS);
    poll(job_id);
  } catch (e) {
    $("status").textContent = "Error: " + e.message;
    $("btn-draft").disabled = false;
  }
}

async function poll(jobId) {
  try {
    const snap = await (await fetch(`/api/draft/${jobId}`)).json();
    if (snap.retrieval) renderRetrieval(snap.retrieval);
    renderPipeline(snap);

    if (snap.status === "done") {
      clearInterval(polling);
      renderGrant(snap);
      $("btn-draft").disabled = false;
    } else if (snap.status === "error") {
      clearInterval(polling);
      $("status").textContent = "Error: " + snap.error;
      $("btn-draft").disabled = false;
    }
  } catch (e) {
    clearInterval(polling);
    $("status").textContent = "Lost the job: " + e.message;
    $("btn-draft").disabled = false;
  }
}

$("btn-sample").addEventListener("click", loadSample);
$("btn-draft").addEventListener("click", draft);
for (const f of ["f-title", "f-class", "f-summary", "f-details"]) {
  $(f).addEventListener("input", schedulePreview);
}
health();
// `/#autodraft` runs the sample straight through on load — for rehearsing the
// demo (docs/DEMO-RUNBOOK.md asks for two run-throughs) without a click.
loadSample().then(() => { if (location.hash === "#autodraft") draft(); });
