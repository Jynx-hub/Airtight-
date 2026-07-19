import React from 'react';
import * as api from './api.js';
import { Badge, Button, Card, Meter, StatReadout } from './ds/index.js';
import { Bar, Empty, Note, PanelBody, Seam, SubLabel, mono, rowRule, th, useLoad } from './common.jsx';
import { CorpusGraph } from './CorpusGraph.jsx';

/* Engine — what the system knows, what it learned, what it measured.
 *
 * Every panel reads committed artifacts off disk. Where an artifact is missing,
 * stale, or synthetic, the panel says so in place rather than rendering a
 * confident number that isn't one. Panels load independently so one bad
 * artifact can't blank the page. */

/* ================= corpus + learning ================= */

function CorpusPanel({ stats }) {
  const c = stats.corpus;
  const byStatute = Object.entries(c.by_statute).sort((a, b) => b[1] - a[1]);
  const byClass = Object.entries(c.by_class).sort((a, b) => b[1] - a[1]);
  const stMax = Math.max(...byStatute.map((x) => x[1]), 1);
  const ccMax = Math.max(...byClass.map((x) => x[1]), 1);

  return (
    <Card title="Retrieval corpus" meta={c.source} eyebrow>
      <StatReadout style={{ marginBottom: 22 }} items={[
        { value: c.count, label: 'records' },
        { value: byStatute.length, label: 'statutes', tone: 'ink' },
        { value: byClass.length, label: 'cpc classes', tone: 'ink' },
      ]} />

      {c.seam && <Seam seam={c.seam} style={{ marginBottom: 22 }} />}

      <CorpusGraph byStatute={c.by_statute} byClass={c.by_class} />

      <SubLabel style={{ marginTop: 26 }}>By statute</SubLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 22 }}>
        {byStatute.map(([k, v]) => <Bar key={k} label={`§${k}`} value={v} max={stMax} />)}
      </div>

      <SubLabel>By CPC class</SubLabel>
      <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
        {byClass.map(([k, v]) => <Bar key={k} label={k} value={v} max={ccMax} tone="deep" />)}
      </div>
    </Card>
  );
}

function LearnedPanel({ stats }) {
  const { episodes, ingested } = stats;
  return (
    <Card title="What it has learned" meta={`episodes ${episodes.enabled ? 'on' : 'off'}`} eyebrow>
      <StatReadout style={{ marginBottom: 24 }} items={[
        { value: episodes.count, label: 'episodes', tone: episodes.count ? undefined : 'muted' },
        { value: episodes.lessons, label: 'lessons distilled', tone: episodes.lessons ? undefined : 'muted' },
        { value: ingested.count, label: 'ingested records', tone: ingested.count ? undefined : 'muted' },
      ]} />

      <Note style={{ marginBottom: 22 }}>
        Compounding runs on a trust gradient: ground truth 1.0, self-distilled lessons 0.5,
        records inferred from ingested documents 0.3. Only records at 1.0 get a reserved
        statute slot — everything below competes on rank alone, so a self-generated lesson
        can never evict a real office-action record just by owning a sparse statute.
      </Note>

      <div style={{ display: 'flex', flexDirection: 'column', gap: 16 }}>
        <Seam seam={episodes.seam} />
        <Seam seam={ingested.seam} />
      </div>
    </Card>
  );
}

/* ================= retrieval inspector ================= */

function InspectorTable({ r }) {
  const rows = [
    ...r.selected.map((rec) => ({ rec, over: false })),
    ...r.runners_up.map((rec) => ({ rec, over: true })),
  ];
  return (
    <table style={{ width: '100%', borderCollapse: 'collapse' }}>
      <thead>
        <tr>
          <th style={{ ...th, width: 60 }}>Rank</th>
          <th style={{ ...th, width: 54 }}>§</th>
          <th style={{ ...th, width: 100 }}>Score</th>
          <th style={{ ...th, width: 110 }}>Won by</th>
          <th style={th}>Matched terms</th>
        </tr>
      </thead>
      <tbody>
        {rows.map(({ rec, over }, i) => {
          const td = { padding: '12px 14px', borderBottom: rowRule(i === rows.length - 1), ...mono, verticalAlign: 'top' };
          const dim = over ? 'var(--faint)' : null;
          return (
            <tr key={i}>
              <td style={{ ...td, color: dim || 'var(--muted-2)' }}>#{rec.rank}</td>
              <td style={{ ...td, color: dim || 'var(--forest)' }}>§{rec.statute}</td>
              <td style={{ ...td, color: dim || 'var(--forest)' }}>{rec.score}</td>
              <td style={{ ...td, fontFamily: 'var(--font-sans)', color: dim || 'var(--ink-2)' }}>
                {over ? 'passed over' : rec.won_by}
              </td>
              <td style={{ ...td, color: dim || 'var(--muted)', lineHeight: 1.5 }}>
                {rec.terms.join(' ') || (over ? '—' : 'class match only')}
              </td>
            </tr>
          );
        })}
      </tbody>
    </table>
  );
}

function InspectorPanel() {
  const list = useLoad(api.disclosures);
  const [picked, setPicked] = React.useState('');
  const [result, setResult] = React.useState(null);
  const [busy, setBusy] = React.useState(false);
  const [error, setError] = React.useState(null);

  const run = React.useCallback(async (id) => {
    if (!id) return;
    setBusy(true);
    setError(null);
    try {
      setResult(await api.retrieveById(id));
    } catch (e) {
      setError(e);
    } finally {
      setBusy(false);
    }
  }, []);

  // Land on a populated panel, not an empty one.
  React.useEffect(() => {
    const first = list.data?.disclosures?.[0];
    if (first && !picked) { setPicked(first.id); run(first.id); }
  }, [list.data, picked, run]);

  const total = list.data?.total ?? 0;
  const options = list.data?.disclosures?.slice(0, 200) ?? [];

  return (
    <Card title="Retrieval inspector" meta={`${total} disclosures on disk`} eyebrow>
      <PanelBody loading={list.loading} error={list.error} what="The disclosure list">
        {list.data?.seam
          ? <Seam seam={list.data.seam} />
          : (
            <>
              <div style={{ display: 'flex', gap: 12, marginBottom: 24, flexWrap: 'wrap' }}>
                <div style={{ position: 'relative', minWidth: 380, flex: 1, maxWidth: 460 }}>
                  <select
                    value={picked}
                    onChange={(e) => { setPicked(e.target.value); run(e.target.value); }}
                    style={selectStyle}
                  >
                    {options.map((d) => (
                      <option key={d.id} value={d.id}>
                        {d.id} · {d.technology_class} · {d.title.slice(0, 60)}
                      </option>
                    ))}
                  </select>
                  <span style={{ position: 'absolute', right: 14, top: '50%', transform: 'translateY(-50%)', color: 'var(--muted-2)', pointerEvents: 'none' }}>▾</span>
                </div>
                <Button variant="ghost" disabled={busy} onClick={() => run(picked)}>Retrieve</Button>
              </div>

              {busy && <Empty pulsing>ranking…</Empty>}
              {error && <Note tone="defect">Retrieval failed: {String(error.message)}</Note>}

              {!busy && !error && result && (
                <>
                  <StatReadout style={{ marginBottom: 22 }} items={[
                    { value: result.selected.length, label: 'selected' },
                    { value: result.statutes_covered.length, label: 'statutes', tone: 'ink' },
                    { value: result.corpus_size, label: 'scored', tone: 'ink' },
                  ]} />

                  {result.self_retrieval_warning && (
                    <Note tone="defect" style={{ marginBottom: 22 }}>
                      Self-retrieval: a record mined from this same application was retrieved.
                      Expected when aiming the inspector at a corpus disclosure — the ablation's
                      holdout split is what prevents this during a graded run.
                    </Note>
                  )}

                  <InspectorTable r={result} />

                  {/* Only claim diversification cost something if it actually did.
                      runners_up are the next records in rank order, not by
                      construction records that beat a pick. */}
                  <Note style={{ marginTop: 24 }}>
                    {result.ranking.algorithm}, k1={result.ranking.k1} b={result.ranking.b}.{' '}
                    {result.runners_up_outscored_a_pick
                      ? 'Dimmed rows out-scored at least one selected record and were still passed over — their statute bucket was already served. That trade is the point: breadth across failure modes beats depth in one.'
                      : 'Dimmed rows are the next records in rank order; none out-scored a pick, so diversification cost nothing here — the top k already spanned the statutes it found.'}
                    {result.class_reordered && ' Score is BM25 only; CPC-class match sorts ahead of it, so a lower-scoring in-class record can outrank a higher-scoring one.'}
                  </Note>
                </>
              )}
            </>
          )}
      </PanelBody>
    </Card>
  );
}

/* ================= failure library ================= */

// A corpus browse is for sampling and filtering, not for reading end to end —
// so the table opens at a page and the filters above it do the narrowing.
const LIBRARY_PAGE = 8;

function FailureLibrary({ stats }) {
  const [filters, setFilters] = React.useState({ statute: '', cpc: '', q: '' });
  const [data, setData] = React.useState(null);
  const [error, setError] = React.useState(null);
  const [expanded, setExpanded] = React.useState(false);
  const debounce = React.useRef(null);

  React.useEffect(() => {
    clearTimeout(debounce.current);
    debounce.current = setTimeout(() => {
      api.memoryRecords(filters).then(setData).catch(setError);
    }, 250);
    return () => clearTimeout(debounce.current);
  }, [filters]);

  // A new filter is a new result set — collapse, or the page opens mid-scroll
  // on rows the user never asked to see.
  React.useEffect(() => setExpanded(false), [filters]);

  const set = (k) => (e) => setFilters((f) => ({ ...f, [k]: e.target.value }));
  const statutes = Object.keys(stats.corpus.by_statute).sort();
  const classes = Object.keys(stats.corpus.by_class).sort();

  const rows = data ? (expanded ? data.records : data.records.slice(0, LIBRARY_PAGE)) : [];
  const hidden = data ? data.records.length - rows.length : 0;

  return (
    <Card title="Failure library" meta={data ? `${rows.length} of ${data.total}` : '—'} eyebrow>
      <div style={{ display: 'flex', gap: 12, marginBottom: 20, flexWrap: 'wrap' }}>
        <select value={filters.statute} onChange={set('statute')} style={{ ...selectStyle, minWidth: 140, maxWidth: 160 }}>
          <option value="">all statutes</option>
          {statutes.map((s) => <option key={s} value={s}>§{s}</option>)}
        </select>
        <select value={filters.cpc} onChange={set('cpc')} style={{ ...selectStyle, minWidth: 130, maxWidth: 150 }}>
          <option value="">all CPC</option>
          {classes.map((s) => <option key={s} value={s}>{s}</option>)}
        </select>
        <input
          value={filters.q}
          onChange={set('q')}
          placeholder="search pattern or claim text"
          style={{
            flex: 1, minWidth: 240, fontFamily: 'var(--font-sans)', fontSize: 'var(--text-body)',
            color: 'var(--ink)', background: 'var(--card)', border: '1px solid var(--border-strong)',
            borderRadius: 'var(--radius-md)', padding: '0.55rem 0.85rem', outline: 'none',
          }}
        />
      </div>

      {error && <Note tone="defect">Could not read the corpus: {String(error.message)}</Note>}
      {!error && !data && <Empty pulsing>loading…</Empty>}

      {data && (data.records.length === 0
        ? <Empty>nothing matches</Empty>
        : (
          <div style={{ overflowX: 'auto' }}>
            <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 720 }}>
              <thead>
                <tr>
                  <th style={{ ...th, width: 54 }}>§</th>
                  <th style={{ ...th, width: 190 }}>ID</th>
                  <th style={{ ...th, width: 70 }}>CPC</th>
                  <th style={th}>Failure mode · rejected claim language</th>
                  <th style={{ ...th, width: 60, textAlign: 'right' }}>Conf</th>
                </tr>
              </thead>
              <tbody>
                {rows.map((rec, i) => {
                  const td = { padding: 14, borderBottom: rowRule(i === rows.length - 1), verticalAlign: 'top' };
                  return (
                    <tr key={rec.id + i}>
                      <td style={{ ...td, ...mono, color: 'var(--forest)' }}>§{rec.statute}</td>
                      <td style={{ ...td, ...mono, color: 'var(--muted)', wordBreak: 'break-all' }}>{rec.id}</td>
                      <td style={{ ...td, ...mono, color: 'var(--muted)' }}>{rec.technology_class}</td>
                      <td style={td}>
                        {/* The claim shape is the useful half of a record — it's the
                            language that actually got rejected. The pattern alone
                            repeats across the corpus. */}
                        <div style={{ fontWeight: 'var(--weight-medium)', fontSize: 'var(--text-body)', color: 'var(--ink-2)', marginBottom: 5 }}>
                          {rec.pattern.slice(0, 120)}
                        </div>
                        <div style={{ ...mono, color: 'var(--muted)', lineHeight: 1.5 }}>
                          {rec.claim_shape.slice(0, 170).replace(/\s+/g, ' ')}…
                        </div>
                      </td>
                      <td style={{ ...td, ...mono, color: 'var(--forest)', textAlign: 'right' }}>{rec.confidence}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>

            {(hidden > 0 || expanded) && (
              <div style={{ paddingTop: 14 }}>
                <button
                  onClick={() => setExpanded((v) => !v)}
                  style={{ ...mono, color: 'var(--muted-2)', background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
                >
                  {expanded ? `▾ Show fewer` : `▸ Show ${hidden} more`}
                </button>
                {/* The fetch itself is capped, so "all" here means all that were
                    read — say so rather than implying the corpus is exhausted. */}
                {expanded && data.total > data.records.length && (
                  <span style={{ ...mono, color: 'var(--muted-2)', marginLeft: 12 }}>
                    · {data.total - data.records.length} beyond the read limit — filter to reach them
                  </span>
                )}
              </div>
            )}
          </div>
        ))}
    </Card>
  );
}

/* ================= ablation ================= */

function AblationPanel() {
  const { loading, data, error } = useLoad(api.ablation);

  return (
    <Card
      title="Ablation · empty vs warmed"
      meta={data?.selected ? `${data.selected.id} · ${data.selected.kind} · ${data.selected.fingerprint.mode} · corpus ${data.selected.corpus_size}` : '—'}
      eyebrow
    >
      <PanelBody loading={loading} error={error} what="The ablation results">
        {!data?.selected ? (
          <Seam seam={data?.seam || { label: 'NO COMPLETE RUN', detail: 'No results.json on disk.', source: 'python -m agent.eval' }} />
        ) : (() => {
          const run = data.selected;
          const t = run.totals;
          // Sign the delta rather than prefixing "+". The repaired number is
          // negative, and a hardcoded "+" rendered it as "+-4".
          const delta = t.warmed.caught - t.empty.caught;
          const byDisc = {};
          for (const r of run.results) (byDisc[r.disclosure_id] ||= {})[r.condition] = r;
          const incomplete = data.runs.filter((r) => !r.complete);

          return (
            <>
              <StatReadout style={{ marginBottom: 24 }} items={[
                { value: `${t.empty.caught}/${t.empty.checklist}`, label: 'caught · empty', tone: 'muted' },
                { value: `${t.warmed.caught}/${t.warmed.checklist}`, label: 'caught · warmed' },
                { value: `${delta > 0 ? '+' : ''}${delta}`, label: 'delta', tone: delta < 0 ? 'defect' : undefined },
                { value: run.disclosures_completed, label: 'disclosures', tone: 'ink' },
              ]} />

              {/* The headline caveat rides directly under the headline number. */}
              <Seam seam={data.caveat} style={{ marginBottom: 24 }} />

              <SubLabel>Per disclosure · loopholes caught</SubLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 16, marginBottom: 24 }}>
                {Object.entries(byDisc).map(([id, arms]) => {
                  const size = arms.warmed?.checklist_size || arms.empty?.checklist_size || 1;
                  return (
                    <div key={id} style={{ paddingTop: 14, borderTop: '1px solid var(--border)' }}>
                      <div style={{ ...mono, color: 'var(--muted)', marginBottom: 8 }}>{id}</div>
                      <div style={{ display: 'flex', flexDirection: 'column', gap: 6 }}>
                        <Bar label="empty" value={arms.empty?.loopholes_caught ?? 0} max={size} tone="muted" />
                        <Bar label="warmed" value={arms.warmed?.loopholes_caught ?? 0} max={size} />
                      </div>
                    </div>
                  );
                })}
              </div>

              {/* Time deltas from this run are one 257s outlier on the empty arm —
                  WORKSTREAMS rules them out as a claim, so they are shown but
                  explicitly not headlined. */}
              <Note style={{ marginBottom: 20 }}>
                Drafting time: empty {t.empty.seconds}s vs warmed {t.warmed.seconds}s. Not a
                claim — the empty arm's total is dominated by one 257s outlier, so the
                aggregate is not a speedup measurement.
              </Note>

              {incomplete.length > 0 && <Seam seam={incomplete[0].seam} />}
            </>
          );
        })()}
      </PanelBody>
    </Card>
  );
}

/* ================= guardrail bus ================= */

// The tail the server hands back is 40 hops deep. The panel's job is to show
// that the bus is live and what it did — the recent few carry that; the rest is
// scrollback, so it opens collapsed like the failure library does.
const BUS_PAGE = 8;

function GuardrailPanel({ onLed }) {
  const { loading, data, error } = useLoad(api.security);
  const [expanded, setExpanded] = React.useState(false);

  React.useEffect(() => {
    if (data) onLed?.({ label: 'BUS', value: data.enabled ? 'live' : 'off', state: data.enabled ? 'on' : 'off' });
  }, [data, onLed]);

  return (
    <Card title="Guardrail bus · 5 hops" meta={data ? `${data.counts.audit} hops analyzed` : '—'} eyebrow>
      <PanelBody loading={loading} error={error} what="The guardrail bus">
        {data && (() => {
          const max = Math.max(1, ...Object.values(data.matrix).map((row) => Object.values(row).reduce((a, b) => a + b, 0)));
          const segColor = (action) =>
            action === 'block' ? 'var(--defect)'
            : action === 'pass' ? 'var(--muted-2)'
            : action === 'redact' ? 'var(--forest-deep)'
            : 'var(--forest)';
          const shown = expanded ? data.events : data.events.slice(0, BUS_PAGE);
          const hidden = data.events.length - shown.length;
          return (
            <>
              <StatReadout style={{ marginBottom: 24 }} items={[
                { value: data.counts.live, label: 'live events', tone: data.counts.live ? undefined : 'muted' },
                { value: data.counts.quarantine, label: 'quarantined' },
                { value: data.counts.escalations, label: 'escalated', tone: 'defect' },
              ]} />

              <SubLabel>Hops × actions</SubLabel>
              <div style={{ display: 'flex', flexDirection: 'column', gap: 8, marginBottom: 16 }}>
                {data.hops.map((hop) => {
                  const row = data.matrix[hop];
                  const total = Object.values(row).reduce((a, b) => a + b, 0);
                  return (
                    <div key={hop} style={{ display: 'grid', gridTemplateColumns: '92px 1fr 34px', alignItems: 'center', gap: 12 }}>
                      <span style={{ ...mono, color: 'var(--muted)' }}>{hop.replace(/_/g, ' ')}</span>
                      {/* One stacked bar per hop so the action mix is visible, not just the volume. */}
                      <div style={{ height: 10, background: 'var(--track)', borderRadius: 3, overflow: 'hidden', display: 'flex' }}>
                        {data.actions.filter((a) => row[a]).map((a) => (
                          <div key={a} title={`${a}: ${row[a]}`} style={{ width: `${(row[a] / max) * 100}%`, height: '100%', background: segColor(a) }} />
                        ))}
                      </div>
                      <span style={{ ...mono, color: 'var(--muted-2)', textAlign: 'right' }}>{total}</span>
                    </div>
                  );
                })}
              </div>

              <p style={{ margin: '0 0 20px', ...mono, color: 'var(--muted-2)', lineHeight: 1.5 }}>
                pass · redact · quarantine · block (fail-closed on tool_call + ingested_document)
              </p>

              <div style={{ display: 'flex', flexDirection: 'column', gap: 2, marginBottom: 20 }}>
                {shown.map((e, i) => (
                  <div key={i} style={{ display: 'flex', alignItems: 'center', gap: 12, padding: '7px 0', borderBottom: rowRule(i === shown.length - 1) }}>
                    <span style={{ ...mono, color: 'var(--muted-2)', width: 62, flex: 'none' }}>{(e.ts || '').slice(11, 19)}</span>
                    <span style={{ width: 96, flex: 'none' }}>
                      <Badge tone={e.action === 'block' ? 'defect' : e.action === 'quarantine' ? 'ink' : e.action === 'redact' ? 'accent' : 'neutral'}>
                        {e.action}
                      </Badge>
                    </span>
                    <span style={{ ...mono, color: 'var(--ink-2)' }}>
                      {e.hop}{e.source ? ' ' + e.source : ''}{e.categories?.length ? ' — ' + e.categories.join(',') : ''}
                    </span>
                  </div>
                ))}

                {(hidden > 0 || expanded) && (
                  <div style={{ paddingTop: 12 }}>
                    <button
                      onClick={() => setExpanded((v) => !v)}
                      style={{ ...mono, color: 'var(--muted-2)', background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}
                    >
                      {expanded ? '▾ Show fewer' : `▸ Show ${hidden} more`}
                    </button>
                    {/* The tail is capped server-side, so an expanded list is not
                        the whole log — say so rather than implying it is. */}
                    {expanded && data.counts.audit > data.events.length && (
                      <span style={{ ...mono, color: 'var(--muted-2)', marginLeft: 12 }}>
                        · {data.counts.audit - data.events.length} older hops beyond the tail
                      </span>
                    )}
                  </div>
                )}
              </div>

              <Seam seam={data.provenance_seam} />
            </>
          );
        })()}
      </PanelBody>
    </Card>
  );
}

/* ================= throughput ================= */

/** Throughput curve as inline SVG — no chart library, no CDN (CSP-proof, offline). */
function Curve({ sweep }) {
  const levels = sweep.levels || [];
  // A one-level smoke sweep divides by zero here and a zero-level one throws on
  // levels[0]; either way the panel silently dies. The server already marks
  // these unplottable — this is the belt to that braces.
  if (levels.length < 2) {
    return <Empty>Only {levels.length} concurrency level in this sweep — nothing to curve.</Empty>;
  }

  const W = 600, H = 250, padL = 44, padR = 20, padT = 34, padB = 30;
  const maxTok = Math.max(...levels.map((l) => l.aggregate_tok_s)) || 1;
  const px = (i) => padL + i * ((W - padL - padR) / (levels.length - 1));
  const py = (v) => H - padB - (v / maxTok) * (H - padT - padB);
  const pts = levels.map((l, i) => `${px(i)},${py(l.aggregate_tok_s)}`).join(' ');
  const kneeIdx = sweep.max_num_seqs ? levels.findIndex((l) => l.concurrency === sweep.max_num_seqs) : -1;

  return (
    <div data-om-raster="true" style={{ width: '100%' }}>
      <svg
        viewBox={`0 0 ${W} ${H}`}
        style={{ width: '100%', height: 'auto', display: 'block' }}
        fontFamily="var(--font-mono)"
        role="img"
        aria-label={`Aggregate throughput from ${levels[0].aggregate_tok_s} to ${maxTok} tokens per second`}
      >
        <text x={padL} y={18} fill="var(--muted-2)" fontSize="12">tok/s</text>
        {/* Mark the configured batch cap — the argument is that the curve bends here. */}
        {kneeIdx >= 0 && (
          <>
            <line x1={px(kneeIdx)} y1={padT} x2={px(kneeIdx)} y2={H - padB} stroke="var(--forest-deep)" strokeWidth="1" strokeDasharray="3 3" />
            {/* Anchored at the foot of the rule, not the head: the knee is where
                the curve is highest, so a label at the top collides with that
                point's own value. Below it, the plot is empty. */}
            <text x={px(kneeIdx) - 6} y={H - padB - 8} textAnchor="end" fill="var(--forest-deep)" fontSize="11">
              max-num-seqs {sweep.max_num_seqs}
            </text>
          </>
        )}
        <polyline points={pts} fill="none" stroke="var(--forest)" strokeWidth="2.5" strokeLinejoin="round" strokeLinecap="round" />
        {levels.map((l, i) => (
          <g key={i}>
            <circle cx={px(i)} cy={py(l.aggregate_tok_s)} r="3.5" fill="var(--forest)" />
            <text x={px(i)} y={py(l.aggregate_tok_s) - 10} textAnchor="middle" fill="var(--ink-2)" fontSize="12">
              {Math.round(l.aggregate_tok_s)}
            </text>
            <text x={px(i)} y={H - 10} textAnchor="middle" fill="var(--muted-2)" fontSize="12">C{l.concurrency}</text>
          </g>
        ))}
      </svg>
    </div>
  );
}

function ThroughputPanel() {
  const { loading, data, error } = useLoad(api.throughput);
  const sw = data?.selected;

  return (
    <Card
      title="Throughput · vLLM batching"
      meta={sw?.max_num_seqs ? `max-num-seqs ${sw.max_num_seqs}` : '—'}
      eyebrow
    >
      <PanelBody loading={loading} error={error} what="The benchmark sweeps">
        {!sw ? (
          <Seam seam={data?.seam || { label: 'NO SWEEP', detail: 'No benchmark on disk.', source: 'python runtime/bench.py' }} />
        ) : (
          <>
            <StatReadout style={{ marginBottom: 26 }} items={[
              { value: `${sw.summary.headline_speedup_x}×`, label: 'aggregate speedup' },
              { value: sw.summary.baseline_tok_s, label: 'tok/s @ C=1', tone: 'ink' },
              { value: sw.summary.operating_point_tok_s, label: `tok/s @ C=${sw.summary.knee_concurrency ?? 16}`, tone: 'ink' },
            ]} />
            <Curve sweep={sw} />
            <Note style={{ margin: '24px 0 20px' }}>
              {sw.has_knee
                ? `Knee at C=${sw.summary.knee_concurrency} — exactly the pinned --max-num-seqs. Past it, throughput adds ~4% while latency nearly doubles: the cap measured is the cap configured.`
                : 'No knee on this profile — C=32 still adds throughput, so the plateau claim belongs to the A100 run only.'}
            </Note>
            <div style={{ ...mono, color: 'var(--muted-2)', lineHeight: 1.7 }}>
              {sw.gpu}
              {sw.notes && <><br />{sw.notes}</>}
            </div>
          </>
        )}
      </PanelBody>
    </Card>
  );
}

/* ================= containment ================= */

function ContainmentPanel() {
  const { loading, data, error } = useLoad(api.containment);

  return (
    <Card title="Containment · four enforcement tiers" meta="NemoClaw / OpenShell" eyebrow>
      <PanelBody loading={loading} error={error} what="The containment policy">
        {data && (
          <>
            {data.error && <Note tone="defect" style={{ marginBottom: 24 }}>{data.error}</Note>}

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1.15fr)', gap: 40, alignItems: 'start' }}>
              <div>
                {data.tiers.map((t, i) => (
                  <div key={t.tier} style={{ padding: '18px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border)' }}>
                    <div style={{ display: 'flex', gap: 8, marginBottom: 10 }}>
                      {/* Red is reserved for defects and blocks. `static` is a property,
                          not a problem — the notable tier is the hot-reloadable one, so
                          accent goes there. */}
                      <Badge tone="accent">{t.tier}</Badge>
                      <Badge tone={t.mutability === 'dynamic' ? 'accent' : 'outline'}>{t.mutability}</Badge>
                    </div>
                    <p style={{ margin: 0, ...mono, color: 'var(--muted)', lineHeight: 1.5 }}>{t.boundary}</p>
                  </div>
                ))}
              </div>

              <div>
                <SubLabel>Network policy · as written</SubLabel>
                <div style={{ overflowX: 'auto' }}>
                  <table style={{ width: '100%', borderCollapse: 'collapse', minWidth: 380 }}>
                    <thead>
                      <tr>
                        <th style={th}>Host</th>
                        <th style={{ ...th, width: 90 }}>Mode</th>
                        <th style={th}>Rules</th>
                      </tr>
                    </thead>
                    <tbody>
                      {data.endpoints.map((e, i) => {
                        const td = { padding: '11px 12px', borderBottom: rowRule(i === data.endpoints.length - 1), verticalAlign: 'top', ...mono };
                        const bare = !e.allow.length && !e.deny.length && !e.access;
                        return (
                          <tr key={e.host + i}>
                            <td style={{ ...td, color: 'var(--ink-2)', wordBreak: 'break-all' }}>{e.host}</td>
                            <td style={{ ...td, color: 'var(--muted)' }}>{e.enforcement || '—'}</td>
                            <td style={{ ...td, color: 'var(--muted)' }}>
                              {e.allow.map((a, j) => <div key={'a' + j}>allow {a}</div>)}
                              {e.deny.map((d, j) => <div key={'d' + j} style={{ color: 'var(--defect)' }}>deny {d}</div>)}
                              {e.access && <div>{e.access}</div>}
                              {bare && <div>—</div>}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              </div>
            </div>

            <Note style={{ margin: '28px 0 24px' }}>
              Every endpoint ships enforcement: audit — audit logs violations and lets traffic
              through, it is not an approval gate. Flip to enforce for the judged run. Unmatched
              requests then default-deny into the Policy Advisor flow; the filing POST matches a
              deny_rule and cannot be escalated at all.
            </Note>

            <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 16 }}>
              <Seam seam={data.enforcement_seam} />
              <Seam seam={data.gateway_seam} />
            </div>
          </>
        )}
      </PanelBody>
    </Card>
  );
}

/* ================= frame ================= */

export function Engine({ onLed }) {
  const stats = useLoad(api.memoryStats);

  React.useEffect(() => {
    if (stats.data) onLed?.({ label: 'CORPUS', value: String(stats.data.corpus.count), state: 'on' });
  }, [stats.data, onLed]);

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 24 }}>
      <PanelBody loading={stats.loading} error={stats.error} what="The corpus statistics">
        {stats.data && (
          <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.15fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}>
            <CorpusPanel stats={stats.data} />
            <LearnedPanel stats={stats.data} />
          </div>
        )}
      </PanelBody>

      <InspectorPanel />

      {stats.data && <FailureLibrary stats={stats.data} />}

      <AblationPanel />

      <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1fr) minmax(0, 1fr)', gap: 24, alignItems: 'start' }}>
        <GuardrailPanel onLed={onLed} />
        <ThroughputPanel />
      </div>

      <ContainmentPanel />
    </div>
  );
}

const selectStyle = {
  width: '100%',
  appearance: 'none',
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-body)',
  color: 'var(--ink)',
  background: 'var(--card)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-md)',
  padding: '0.7rem 2rem 0.7rem 0.85rem',
  cursor: 'pointer',
  outline: 'none',
};
