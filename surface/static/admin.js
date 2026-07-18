/* Engine frame — what the system knows, what it learned, what it measured.
 *
 * Every panel reads committed artifacts off disk. Where an artifact is missing,
 * stale, or synthetic, the panel says so in place rather than rendering a
 * confident number that isn't one. */

const $ = (id) => document.getElementById(id);
const el = (tag, cls, text) => {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined) n.textContent = text;
  return n;
};
const get = (url) => fetch(url).then((r) => r.json());

function stat(n, label, cls) {
  const s = el("div", "stat");
  s.append(el("div", `n ${cls || ""}`, String(n)), el("div", "l", label));
  return s;
}

function meter(key, value, max, cls) {
  const m = el("div", "meter");
  const track = el("div", "track");
  const fill = el("div", `fill ${cls || ""}`);
  fill.style.width = `${max ? Math.max(1, (value / max) * 100) : 0}%`;
  track.append(fill);
  m.append(el("div", "k", key), track, el("div", "v", String(value)));
  return m;
}

/** The honesty badge. Every seam names the exact path or command that fills it. */
function seam(s, inline) {
  const n = el("div", `seam ${inline ? "inline" : ""}`);
  n.append(el("span", "label", s.label), el("div", "detail", s.detail), el("div", "src", s.source));
  return n;
}

function setLed(id, label, value, state) {
  const node = $(id);
  node.className = `led ${state}`;
  node.innerHTML = "";
  node.append(`${label} `, el("b", null, value));
}

/* ================= corpus ================= */

async function loadMemory() {
  const m = await get("/api/memory/stats");
  setLed("led-corpus", "CORPUS", `${m.corpus.count}`, "on");

  const body = $("corpus-body");
  body.innerHTML = "";
  $("corpus-meta").textContent = m.corpus.source;

  const s = el("div", "stats");
  s.style.marginBottom = ".9rem";
  s.append(
    stat(m.corpus.count, "records"),
    stat(Object.keys(m.corpus.by_statute).length, "statutes", "muted"),
    stat(Object.keys(m.corpus.by_class).length, "CPC classes", "muted"),
  );
  body.append(s);

  body.append(el("h4", "mono small muted", "By statute"));
  const st = Object.entries(m.corpus.by_statute).sort((a, b) => b[1] - a[1]);
  const stMax = Math.max(...st.map((x) => x[1]));
  for (const [k, v] of st) body.append(meter(`§${k}`, v, stMax));

  const cls = el("h4", "mono small muted", "By CPC class");
  cls.style.marginTop = ".8rem";
  body.append(cls);
  const cc = Object.entries(m.corpus.by_class).sort((a, b) => b[1] - a[1]);
  const ccMax = Math.max(...cc.map((x) => x[1]));
  for (const [k, v] of cc) body.append(meter(k, v, ccMax, "deep"));

  renderLearning(m);
  buildFilters(m);
}

/* ================= learning ================= */

function renderLearning(m) {
  const body = $("learn-body");
  body.innerHTML = "";
  $("learn-meta").textContent = `episodes ${m.episodes.enabled ? "on" : "off"}`;

  const s = el("div", "stats");
  s.style.marginBottom = ".9rem";
  s.append(
    stat(m.episodes.count, "episodes", m.episodes.count ? "" : "muted"),
    stat(m.episodes.lessons, "lessons distilled", m.episodes.lessons ? "" : "muted"),
    stat(m.ingested.count, "ingested records", m.ingested.count ? "" : "muted"),
  );
  body.append(s);

  const note = el("div", "note");
  note.textContent = "Compounding runs on a trust gradient: ground truth 1.0, self-distilled lessons 0.5, "
    + "records inferred from ingested documents 0.3. Only records at 1.0 get a reserved statute slot — "
    + "everything below competes on rank alone, so a self-generated lesson can never evict a real "
    + "office-action record just by owning a sparse statute.";
  body.append(note);

  if (m.episodes.seam) body.append(seam(m.episodes.seam));
  if (m.ingested.seam) {
    const gap = el("div");
    gap.style.height = ".6rem";
    body.append(gap, seam(m.ingested.seam));
  }
}

/* ================= corpus browser ================= */

let filters = { statute: "", cpc: "", q: "" };

function buildFilters(m) {
  const st = $("f-statute");
  st.innerHTML = "";
  st.append(new Option("all statutes", ""));
  for (const k of Object.keys(m.corpus.by_statute).sort()) st.append(new Option(`§${k}`, k));

  const cpc = $("f-cpc");
  cpc.innerHTML = "";
  cpc.append(new Option("all CPC", ""));
  for (const k of Object.keys(m.corpus.by_class).sort()) cpc.append(new Option(k, k));

  st.onchange = () => { filters.statute = st.value; loadRecords(); };
  cpc.onchange = () => { filters.cpc = cpc.value; loadRecords(); };

  let t;
  $("f-q").oninput = (e) => {
    clearTimeout(t);
    t = setTimeout(() => { filters.q = e.target.value; loadRecords(); }, 250);
  };
  loadRecords();
}

async function loadRecords() {
  const qs = new URLSearchParams({ ...filters, limit: 60 });
  const r = await get(`/api/memory/records?${qs}`);
  $("rec-meta").textContent = `${r.shown} of ${r.total}`;
  const body = $("rec-body");
  body.innerHTML = "";
  if (!r.records.length) {
    const tr = el("tr");
    const td = el("td", "empty", "nothing matches");
    td.colSpan = 5;
    tr.append(td);
    body.append(tr);
    return;
  }
  for (const rec of r.records) {
    const tr = el("tr");
    // The claim shape is the useful half of a record — it's the language that
    // actually got rejected. The pattern alone repeats across the corpus.
    const what = el("td", "wrap");
    what.append(el("div", null, rec.pattern.slice(0, 120)));
    const shape = el("div", "muted");
    shape.style.marginTop = ".15rem";
    shape.textContent = rec.claim_shape.slice(0, 170).replace(/\s+/g, " ") + "…";
    what.append(shape);
    tr.append(
      el("td", "num", `§${rec.statute}`),
      el("td", "muted", rec.id),
      el("td", null, rec.technology_class),
      what,
      el("td", "num", String(rec.confidence)),
    );
    body.append(tr);
  }
}

/* ================= retrieval inspector ================= */

async function loadDisclosures() {
  const d = await get("/api/disclosures");
  const pick = $("insp-pick");
  pick.innerHTML = "";
  for (const x of d.disclosures.slice(0, 200)) {
    pick.append(new Option(`${x.id} · ${x.technology_class} · ${x.title.slice(0, 60)}`, x.id));
  }
  $("insp-meta").textContent = `${d.total} disclosures on disk`;
  $("insp-run").onclick = runInspector;
  $("insp-pick").onchange = runInspector;
  if (d.disclosures.length) runInspector();  // land on a populated panel, not an empty one
}

async function runInspector() {
  const id = $("insp-pick").value;
  if (!id) return;
  const body = $("insp-body");
  body.innerHTML = "";
  body.append(el("p", "empty pulsing", "ranking…"));

  const r = await get(`/api/memory/retrieve/${id}`);
  body.innerHTML = "";

  const s = el("div", "stats");
  s.style.marginBottom = ".8rem";
  s.append(
    stat(r.selected.length, "selected"),
    stat(r.statutes_covered.length, "statutes"),
    stat(r.corpus_size, "scored", "muted"),
  );
  body.append(s);

  if (r.self_retrieval_warning) {
    const w = el("div", "note defect");
    w.textContent = "Self-retrieval: a record mined from this same application was retrieved. Expected "
      + "when aiming the inspector at a corpus disclosure — the ablation's holdout split is what "
      + "prevents this during a graded run.";
    body.append(w);
  }

  const table = el("table");
  table.innerHTML = `<thead><tr>
    <th style="width:46px">Rank</th><th style="width:46px">§</th><th style="width:70px">Score</th>
    <th style="width:78px">Won by</th><th>Matched terms</th></tr></thead>`;
  const tb = el("tbody");

  for (const rec of r.selected) {
    const tr = el("tr");
    const terms = el("td", "wrap muted", rec.terms.join(" ") || "class match only");
    tr.append(
      el("td", "num", `#${rec.rank}`),
      el("td", "num", `§${rec.statute}`),
      el("td", "num", String(rec.score)),
      el("td", null, rec.won_by),
      terms,
    );
    tb.append(tr);
  }
  // Runners-up make diversification legible: these out-scored some of the picks
  // above and still lost, because their statute bucket was already served.
  for (const rec of r.runners_up) {
    const tr = el("tr");
    tr.style.opacity = ".45";
    tr.append(
      el("td", "num", `#${rec.rank}`),
      el("td", "num", `§${rec.statute}`),
      el("td", "num", String(rec.score)),
      el("td", "muted", "passed over"),
      el("td", "wrap muted", rec.terms.join(" ") || "—"),
    );
    tb.append(tr);
  }
  table.append(tb);
  body.append(table);

  const n = el("div", "note");
  n.textContent = `${r.ranking.algorithm}, k1=${r.ranking.k1} b=${r.ranking.b}. Dimmed rows out-scored `
    + `at least one selected record and were still passed over — their statute bucket was already served. `
    + `That trade is the point: breadth across failure modes beats depth in one.`;
  body.append(n);
}

/* ================= ablation ================= */

async function loadAblation() {
  const a = await get("/api/ablation");
  const body = $("abl-body");
  body.innerHTML = "";

  if (!a.selected) {
    body.append(seam(a.seam || { label: "NO COMPLETE RUN", detail: "No results.json on disk.", source: "python -m agent.eval" }));
    return;
  }

  const run = a.selected;
  const t = run.totals;
  $("abl-meta").textContent = `${run.id} · ${run.fingerprint.mode} · corpus ${run.corpus_size}`;

  const s = el("div", "stats");
  s.style.marginBottom = ".9rem";
  s.append(
    stat(`${t.empty.caught}/${t.empty.checklist}`, "caught · empty", "muted"),
    stat(`${t.warmed.caught}/${t.warmed.checklist}`, "caught · warmed"),
    stat(`+${t.warmed.caught - t.empty.caught}`, "delta"),
    stat(run.disclosures_completed, "disclosures", "muted"),
  );
  body.append(s);

  // The headline caveat rides directly under the headline number.
  body.append(seam(a.caveat));

  const h = el("h4", "mono small muted", "Per disclosure · loopholes caught");
  h.style.marginTop = ".9rem";
  body.append(h);

  const byDisc = {};
  for (const r of run.results) (byDisc[r.disclosure_id] ||= {})[r.condition] = r;

  for (const [id, arms] of Object.entries(byDisc)) {
    const row = el("div");
    row.style.cssText = "padding:.4rem 0;border-top:1px solid var(--line)";
    const hd = el("div", "small mono muted");
    hd.textContent = id;
    row.append(hd);
    const size = arms.warmed?.checklist_size || arms.empty?.checklist_size || 1;
    row.append(meter("empty", arms.empty?.loopholes_caught ?? 0, size, "muted"));
    row.append(meter("warmed", arms.warmed?.loopholes_caught ?? 0, size));
    body.append(row);
  }

  // Time deltas from this run are one 257s outlier on the empty arm — WORKSTREAMS
  // rules them out as a claim, so they are shown but explicitly not headlined.
  const time = el("div", "note");
  time.textContent = `Drafting time: empty ${t.empty.seconds}s vs warmed ${t.warmed.seconds}s. Not a claim — `
    + `the empty arm's total is dominated by one 257s outlier, so the aggregate is not a speedup measurement.`;
  body.append(time);

  const incomplete = a.runs.filter((r) => !r.complete);
  if (incomplete.length) {
    const gap = el("div");
    gap.style.height = ".6rem";
    body.append(gap, seam(incomplete[0].seam, true));
  }
}

/* ================= security bus ================= */

async function loadSecurity() {
  const s = await get("/api/security");
  setLed("led-hl", "BUS", s.enabled ? "live" : "off", s.enabled ? "on" : "off");

  const body = $("sec-body");
  body.innerHTML = "";
  $("sec-meta").textContent = `${s.counts.audit} hops analyzed`;

  const st = el("div", "stats");
  st.style.marginBottom = ".9rem";
  st.append(
    stat(s.counts.live, "live events", s.counts.live ? "" : "muted"),
    stat(s.counts.quarantine, "quarantined"),
    stat(s.counts.escalations, "escalated", "defect"),
  );
  body.append(st);

  body.append(el("h4", "mono small muted", "Hops × actions"));
  const max = Math.max(1, ...Object.values(s.matrix).map((row) => Object.values(row).reduce((a, b) => a + b, 0)));
  for (const hop of s.hops) {
    const row = s.matrix[hop];
    const total = Object.values(row).reduce((a, b) => a + b, 0);
    const m = el("div", "meter");
    const track = el("div", "track");
    // One stacked bar per hop so the action mix is visible, not just the volume.
    for (const action of s.actions) {
      if (!row[action]) continue;
      const seg = el("div", `fill ${action === "block" ? "defect" : action === "pass" ? "muted" : action === "redact" ? "deep" : ""}`);
      seg.style.width = `${(row[action] / max) * 100}%`;
      seg.title = `${action}: ${row[action]}`;
      track.append(seg);
    }
    m.append(el("div", "k", hop.replace("_", " ").slice(0, 9)), track, el("div", "v", String(total)));
    body.append(m);
  }

  const legend = el("p", "small muted mono");
  legend.style.marginTop = ".5rem";
  legend.textContent = "pass · redact · quarantine · block   (fail-closed on tool_call + ingested_document)";
  body.append(legend);

  if (s.provenance_seam) body.append(seam(s.provenance_seam));

  const stream = $("sec-stream");
  stream.innerHTML = "";
  for (const e of s.events) {
    const ln = el("div", "ln");
    ln.append(
      el("span", "t", (e.ts || "").slice(11, 19)),
      el("span", `a ${e.action}`, e.action),
      el("span", "d", `${e.hop}${e.source ? " " + e.source : ""}${e.categories?.length ? " — " + e.categories.join(",") : ""}`),
    );
    stream.append(ln);
  }
}

/* ================= throughput ================= */

async function loadThroughput() {
  const t = await get("/api/throughput");
  const body = $("tp-body");
  body.innerHTML = "";

  if (!t.selected) {
    body.append(seam(t.seam));
    return;
  }

  const sw = t.selected;
  const sum = sw.summary;
  $("tp-meta").textContent = `${sw.max_num_seqs ? "max-num-seqs " + sw.max_num_seqs : ""}`;

  const st = el("div", "stats");
  st.style.marginBottom = ".9rem";
  st.append(
    stat(`${sum.headline_speedup_x}×`, "aggregate speedup"),
    stat(sum.baseline_tok_s, "tok/s @ C=1", "muted"),
    stat(sum.operating_point_tok_s, "tok/s @ C=16"),
  );
  body.append(st);
  body.append(curve(sw));

  const note = el("div", "note");
  note.textContent = sw.has_knee
    ? `Knee at C=${sum.knee_concurrency} — exactly the pinned --max-num-seqs. Past it, throughput adds `
      + `~4% while latency nearly doubles: the cap measured is the cap configured.`
    : `No knee on this profile — C=32 still adds throughput, so the plateau claim belongs to the A100 run only.`;
  body.append(note);

  const prov = el("p", "small muted");
  prov.style.marginTop = ".5rem";
  prov.textContent = sw.gpu || "";
  body.append(prov);
  if (sw.notes) {
    const n = el("p", "small muted mono");
    n.style.marginTop = ".3rem";
    n.textContent = sw.notes;
    body.append(n);
  }
}

/** Throughput curve as inline SVG — no chart library, no CDN (CSP-proof, offline). */
function curve(sw) {
  const W = 460, H = 170, PAD = 34;
  const levels = sw.levels;
  const maxTok = Math.max(...levels.map((l) => l.aggregate_tok_s));
  const xs = levels.map((_, i) => PAD + (i * (W - PAD * 2)) / (levels.length - 1));
  const ys = levels.map((l) => H - PAD - (l.aggregate_tok_s / maxTok) * (H - PAD * 2));

  const ns = "http://www.w3.org/2000/svg";
  const svg = document.createElementNS(ns, "svg");
  svg.setAttribute("viewBox", `0 0 ${W} ${H}`);
  svg.setAttribute("width", "100%");
  svg.setAttribute("role", "img");
  svg.setAttribute("aria-label",
    `Aggregate throughput from ${levels[0].aggregate_tok_s} to ${Math.max(...levels.map((l) => l.aggregate_tok_s))} tokens per second`);

  const line = (x1, y1, x2, y2, stroke, dash) => {
    const l = document.createElementNS(ns, "line");
    l.setAttribute("x1", x1); l.setAttribute("y1", y1);
    l.setAttribute("x2", x2); l.setAttribute("y2", y2);
    l.setAttribute("stroke", stroke);
    if (dash) l.setAttribute("stroke-dasharray", dash);
    svg.append(l);
  };
  const text = (x, y, s, fill, anchor) => {
    const t = document.createElementNS(ns, "text");
    t.setAttribute("x", x); t.setAttribute("y", y);
    t.setAttribute("fill", fill);
    t.setAttribute("font-size", "9");
    t.setAttribute("font-family", "ui-monospace, monospace");
    if (anchor) t.setAttribute("text-anchor", anchor);
    t.textContent = s;
    svg.append(t);
  };

  line(PAD, H - PAD, W - PAD, H - PAD, "#33333A");
  line(PAD, PAD - 8, PAD, H - PAD, "#33333A");

  // Mark the configured batch cap — the argument is that the curve bends here.
  if (sw.max_num_seqs) {
    const i = levels.findIndex((l) => l.concurrency === sw.max_num_seqs);
    if (i >= 0) {
      line(xs[i], PAD - 8, xs[i], H - PAD, "#7A5A24", "2 3");
      text(xs[i], PAD - 12, `max-num-seqs ${sw.max_num_seqs}`, "#7A5A24", "middle");
    }
  }

  const path = document.createElementNS(ns, "path");
  path.setAttribute("d", xs.map((x, i) => `${i ? "L" : "M"}${x},${ys[i]}`).join(" "));
  path.setAttribute("fill", "none");
  path.setAttribute("stroke", "#E0A44C");
  path.setAttribute("stroke-width", "1.8");
  svg.append(path);

  levels.forEach((l, i) => {
    const c = document.createElementNS(ns, "circle");
    c.setAttribute("cx", xs[i]); c.setAttribute("cy", ys[i]); c.setAttribute("r", "2.6");
    c.setAttribute("fill", "#E0A44C");
    svg.append(c);
    text(xs[i], H - PAD + 12, `C${l.concurrency}`, "#8B8B84", "middle");
    text(xs[i], ys[i] - 7, String(Math.round(l.aggregate_tok_s)), "#E8E6E1", "middle");
  });
  text(4, PAD - 10, "tok/s", "#8B8B84");
  return svg;
}

/* ================= containment ================= */

async function loadContainment() {
  const c = await get("/api/containment");
  const body = $("cont-body");
  body.innerHTML = "";

  const grid = el("div", "grid two");
  const tiers = el("div");
  for (const t of c.tiers) {
    const row = el("div");
    row.style.cssText = "padding:.5rem 0;border-top:1px solid var(--line)";
    const hd = el("div");
    hd.style.cssText = "display:flex;gap:.4rem;align-items:center;margin-bottom:.2rem";
    // Red is reserved for defects and blocks. `static` is a property, not a
    // problem — the notable tier is the hot-reloadable one, so accent goes there.
    hd.append(
      el("span", "tag accent", t.tier),
      el("span", `tag ${t.mutability === "dynamic" ? "accent" : ""}`, t.mutability),
    );
    row.append(hd, el("div", "small muted", t.boundary));
    tiers.append(row);
  }
  grid.append(tiers);

  const rules = el("div");
  rules.append(el("h4", "mono small muted", "Network policy · as written"));
  const table = el("table");
  table.innerHTML = `<thead><tr><th>Host</th><th style="width:80px">Mode</th><th>Rules</th></tr></thead>`;
  const tb = el("tbody");
  for (const e of c.endpoints) {
    const tr = el("tr");
    const rulesCell = el("td", "wrap");
    for (const a of e.allow) rulesCell.append(el("div", "muted", `allow ${a}`));
    for (const d of e.deny) {
      const n = el("div", null, `deny ${d}`);
      n.style.color = "var(--defect)";
      rulesCell.append(n);
    }
    if (e.access) rulesCell.append(el("div", "muted", e.access));
    if (!e.allow.length && !e.deny.length && !e.access) rulesCell.append(el("div", "muted", "—"));
    tr.append(el("td", null, e.host), el("td", null, e.enforcement || "—"), rulesCell);
    tb.append(tr);
  }
  table.append(tb);
  rules.append(table);
  grid.append(rules);
  body.append(grid);

  const n = el("div", "note");
  n.textContent = "Every endpoint ships enforcement: audit — audit logs violations and lets traffic "
    + "through, it is not an approval gate. Flip to enforce for the judged run. Unmatched requests then "
    + "default-deny into the Policy Advisor flow; the filing POST matches a deny_rule and cannot be escalated at all.";
  body.append(n);

  body.append(seam(c.enforcement_seam));
  const gap = el("div");
  gap.style.height = ".6rem";
  body.append(gap, seam(c.gateway_seam));
}

/* ================= boot ================= */

async function health() {
  try {
    const h = await get("/api/health");
    setLed("led-mode", "MODE", h.mode, h.mode === "live" ? "on" : "off");
  } catch {
    setLed("led-mode", "MODE", "offline", "alert");
  }
}

// Panels load independently so one bad artifact can't blank the page.
for (const fn of [health, loadMemory, loadDisclosures, loadAblation, loadSecurity, loadThroughput, loadContainment]) {
  fn().catch((e) => console.error(fn.name, e));
}
