import React from 'react';
import * as api from './api.js';
import { Badge, Button, Callout, StatReadout, TextArea, TextField } from './ds/index.js';
import { Empty, Note, SectionHead, mono, rowRule } from './common.jsx';

/* Intake — disclosure in, context matched, loop watched, patent out.
 *
 * Drafting goes through the job routes rather than the blocking POST: a live
 * draft is several sequential model turns and has been measured at 257s, and
 * the loop's stages are the most interesting thing to look at while it runs. */

const POLL_MS = 400;
const PREVIEW_MS = 350;

const BLANK = { title: '', technology_class: '', inventors: '', summary: '', details: '' };

const toDisclosure = (form) => ({
  id: 'ui-' + Date.now(),
  title: form.title,
  technology_class: form.technology_class,
  inventors: form.inventors.split(',').map((s) => s.trim()).filter(Boolean),
  summary: form.summary,
  details: form.details,
});

/* ---------------- 02 · context match ---------------- */

function MatchRow({ rec, max, first }) {
  return (
    <div style={{
      paddingTop: first ? 4 : 20,
      marginTop: first ? 0 : 20,
      borderTop: first ? 'none' : '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', gap: 8, alignItems: 'center', flexWrap: 'wrap', marginBottom: 10 }}>
        <Badge tone="accent">§{rec.statute}</Badge>
        {rec.class_match && <Badge tone="outline">{rec.technology_class} match</Badge>}
        {rec.confidence < 1 && <Badge tone="outline">conf {rec.confidence}</Badge>}
        {rec.self_retrieval && <Badge tone="defect">self</Badge>}
        <span style={{ ...mono, color: 'var(--muted-2)', marginLeft: 'auto' }}>
          #{rec.rank} · {rec.score}
        </span>
      </div>
      <div style={{ height: 6, background: 'var(--track)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{
          width: Math.max(3, (rec.score / max) * 100) + '%',
          height: '100%',
          background: rec.trusted ? 'var(--forest)' : 'var(--forest-deep)',
          transition: 'width var(--dur-base) var(--ease-standard)',
        }} />
      </div>
      <div style={{ fontSize: 'var(--text-body)', color: 'var(--ink-2)', marginTop: 10 }}>{rec.pattern}</div>
      <div style={{ ...mono, color: 'var(--muted-2)', marginTop: 4 }}>
        {rec.terms.length ? `matched: ${rec.terms.join(' ')}` : 'matched on class only'}
      </div>
    </div>
  );
}

function ContextMatch({ retrieval, live }) {
  if (!retrieval) {
    return (
      <div style={panelSunk}>
        <Empty>Submit a disclosure to see which recorded failure modes it matches.</Empty>
      </div>
    );
  }
  const r = retrieval;
  const max = Math.max(...r.selected.map((s) => s.score), 1);
  return (
    <div style={panelSunk}>
      <div style={{ display: 'flex', flexWrap: 'wrap', gap: 24, alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: 26 }}>
        <StatReadout items={[
          { value: r.selected.length, label: 'retrieved' },
          { value: r.statutes_covered.length, label: 'statutes', tone: 'ink' },
          { value: r.corpus_size, label: 'corpus', tone: 'ink' },
        ]} />
        <p style={{
          margin: 0, maxWidth: 340, fontSize: 'var(--text-body)', lineHeight: 1.55,
          color: 'var(--muted)', borderLeft: '2px solid var(--forest-deep)', paddingLeft: 14,
        }}>
          {r.diversified
            ? `Statute-diversified across §${r.statutes_covered.join(' · §')} — the round-robin takes one record per statute before any statute gets a second, so a §103-heavy corpus can't crowd out §101.`
            : `Only §${r.statutes_covered.join('/')} matched — nothing to diversify across at k=${r.k}.`}
        </p>
      </div>

      {r.self_retrieval_warning && (
        <Note tone="defect" style={{ marginBottom: 22 }}>
          Self-retrieval: at least one record was mined from this same application.
          Expected when demoing with a corpus disclosure — it is the examiner's own
          rejections coming back.
        </Note>
      )}

      <div style={{ display: 'flex', flexDirection: 'column' }}>
        {r.selected.map((rec, i) => <MatchRow key={i} rec={rec} max={max} first={i === 0} />)}
      </div>

      <p style={{
        margin: '24px 0 0', paddingTop: 18, borderTop: '1px solid var(--border)',
        fontSize: 'var(--text-body)', lineHeight: 1.55, color: 'var(--muted-2)',
      }}>
        Ranked by {r.ranking.algorithm} · k1={r.ranking.k1} b={r.ranking.b}. b deviates from
        the literature default 0.75 deliberately: measured, it cuts cross-disclosure overlap
        from 0.104 to 0.098 and keeps self-noise out of the top 10.
      </p>
    </div>
  );
}

/* ---------------- 03 · pipeline ---------------- */

function StageRow({ stage, last }) {
  const [open, setOpen] = React.useState(false);
  const dot = stage.state === 'done' ? 'var(--forest)'
    : stage.state === 'running' ? 'var(--forest)'
    : 'var(--faint)';
  return (
    <div style={{ padding: '14px 0', borderBottom: rowRule(last) }}>
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', flexWrap: 'wrap' }}>
        <span
          className={stage.state === 'running' ? 'pulsing' : undefined}
          style={{ width: 9, height: 9, borderRadius: '50%', background: dot, flex: 'none' }}
        />
        <span style={{ fontWeight: 'var(--weight-semibold)', color: 'var(--ink)' }}>{stage.label}</span>
        <span style={{ fontSize: 'var(--text-body)', color: 'var(--muted)' }}>{stage.detail}</span>
        <span style={{ marginLeft: 'auto' }}>
          <Badge tone={stage.state === 'done' ? 'accent' : 'outline'}>{stage.state}</Badge>
        </span>
      </div>
      {stage.reply && (
        <div style={{ marginTop: 10 }}>
          <button
            onClick={() => setOpen((v) => !v)}
            style={{
              ...mono, color: 'var(--muted-2)', background: 'transparent',
              border: 'none', padding: 0, cursor: 'pointer',
            }}
          >
            {open ? '▾' : '▸'} {stage.reply.length.toLocaleString()} chars
          </button>
          {open && (
            <pre style={{
              ...mono, color: 'var(--muted)', margin: '8px 0 0', maxHeight: 220,
              overflow: 'auto', whiteSpace: 'pre-wrap', wordBreak: 'break-word',
              background: 'var(--surface-sunk)', border: '1px solid var(--border)',
              borderRadius: 'var(--radius-md)', padding: 12,
            }}>{stage.reply}</pre>
          )}
        </div>
      )}
    </div>
  );
}

function Pipeline({ snap }) {
  if (!snap) {
    return (
      <div style={pipelineIdle}>
        <p style={{ margin: 0, fontFamily: 'var(--font-serif)', fontStyle: 'italic', fontSize: 'var(--text-lead)', lineHeight: 1.5, color: 'var(--ink-2)' }}>
          Plan → draft → critique. Airtight keeps revising while the examiner turn still finds a material defect.
        </p>
      </div>
    );
  }
  if (snap.status === 'retrieving') {
    return <div style={pipelineIdle}><Empty pulsing>Matching the disclosure against memory…</Empty></div>;
  }
  if (snap.status === 'queued') {
    // Drafts are serialized process-wide so guardrail findings stay attributable
    // to the request that caused them. Say that rather than looking hung.
    return <div style={pipelineIdle}><Empty pulsing>Queued — another draft holds the model hop.</Empty></div>;
  }
  return (
    <div style={panelCard}>
      {snap.stages.map((s, i) => (
        <StageRow key={i} stage={s} last={i === snap.stages.length - 1} />
      ))}
    </div>
  );
}

/* ---------------- 04 · grant ---------------- */

function ReportSection({ title, items, empty }) {
  return (
    <div style={{ marginBottom: 22 }}>
      <div style={{
        fontFamily: 'var(--font-sans)', fontWeight: 'var(--weight-semibold)',
        fontSize: 'var(--text-sm)', letterSpacing: 'var(--tracking-eyebrow)',
        textTransform: 'uppercase', color: 'var(--muted-2)', marginBottom: 10,
      }}>{title} ({items.length})</div>
      {items.length === 0
        ? <Empty>{empty}</Empty>
        : (
          <ul style={{ margin: 0, paddingLeft: '1.1rem', color: 'var(--muted)', fontSize: 'var(--text-body)', lineHeight: 1.6 }}>
            {items.map((it, i) => <li key={i} style={{ marginBottom: 6 }}>{it}</li>)}
          </ul>
        )}
    </div>
  );
}

function Claims({ jobId, draft }) {
  const [claims, setClaims] = React.useState(draft.claims);
  const [saving, setSaving] = React.useState(false);
  const [status, setStatus] = React.useState('');

  React.useEffect(() => { setClaims(draft.claims); }, [draft]);

  // Claims are editable and edits persist — PATCH /api/draft/{job_id} accepts the
  // steered draft, so a hand-edit is a legitimate final draft, not a discarded one.
  const save = async () => {
    setSaving(true);
    setStatus('Saving…');
    try {
      const snap = await api.patchClaims(jobId, claims);
      setStatus(`Saved ${snap.draft.claims.length} steered claims.`);
    } catch (e) {
      setStatus('Save failed: ' + e.message);
    } finally {
      setSaving(false);
    }
  };

  return (
    <div>
      {claims.map((c, i) => (
        <div key={i} style={{ display: 'grid', gridTemplateColumns: '2rem 1fr', gap: 10, padding: '10px 0', borderTop: i === 0 ? 'none' : '1px solid var(--border)' }}>
          <div style={{ ...mono, color: 'var(--forest)', paddingTop: 10 }}>{i + 1}.</div>
          <textarea
            value={c}
            onChange={(e) => setClaims(claims.map((x, j) => (j === i ? e.target.value : x)))}
            rows={3}
            style={{
              width: '100%', fontFamily: 'var(--font-serif)', fontSize: 'var(--text-body)',
              lineHeight: 1.7, color: 'var(--ink-2)', background: 'var(--card)',
              border: '1px solid var(--border-strong)', borderRadius: 'var(--radius-md)',
              padding: '0.6rem 0.7rem', resize: 'vertical', outline: 'none',
            }}
          />
        </div>
      ))}
      <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 16 }}>
        <Button size="sm" disabled={saving} onClick={save}>Save claim edits</Button>
        <span style={{ fontSize: 'var(--text-body)', color: 'var(--muted)' }}>{status}</span>
      </div>
    </div>
  );
}

function Grant({ jobId, snap }) {
  const { draft, report } = snap;
  const [specOpen, setSpecOpen] = React.useState(false);

  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(0, 1.1fr) minmax(0, 1fr)', gap: 40, alignItems: 'start' }}>
      <div>
        <div style={eyebrowLabel}>Claims</div>
        <Claims jobId={jobId} draft={draft} />

        <div style={{ marginTop: 28 }}>
          <button onClick={() => setSpecOpen((v) => !v)} style={{ ...mono, color: 'var(--muted-2)', background: 'transparent', border: 'none', padding: 0, cursor: 'pointer' }}>
            {specOpen ? '▾' : '▸'} Full specification
          </button>
          {specOpen && (
            <pre style={{
              ...mono, color: 'var(--muted)', margin: '10px 0 0', maxHeight: 420, overflow: 'auto',
              whiteSpace: 'pre-wrap', wordBreak: 'break-word', background: 'var(--surface-sunk)',
              border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', padding: 14,
            }}>{draft.specification}</pre>
          )}
        </div>
      </div>

      <div>
        <div style={eyebrowLabel}>Loophole report</div>
        <ReportSection
          title="Loopholes pre-empted from memory"
          items={report.loopholes_closed}
          empty="no records retrieved — memory is empty for this class"
        />
        <ReportSection
          title="Live prior art to distinguish over · §103"
          items={report.prior_art || []}
          empty="no live prior art — set USPTO_API_KEY for a live search"
        />
        <ReportSection
          title="Smart catches · self-critique"
          items={report.smart_catches}
          empty="the examiner turn raised nothing"
        />

        {/* loopholes_closed is what the drafting turn was primed with, not a verified
            cure. The judge that verifies closure lives in the eval harness and does
            not run on this path — say so rather than implying a graded result. */}
        {report.loopholes_closed.length > 0 && (
          <Note style={{ marginBottom: 22 }}>
            {report.guardrails_applied} recorded failure modes were put in front of the
            drafting turn. Whether each is actually closed is graded by the eval harness
            (agent/eval/judge.py), which does not run here.
          </Note>
        )}

        <div style={eyebrowLabel}>Runtime security</div>
        {!report.security_scanning ? (
          <Callout variant="dashed" label="Scanning off" footer="AIRTIGHT_HL_ENABLED=true">
            HiddenLayer is disabled, so no hop was analyzed. With it on, injections in
            ingested prior art and exfil in tool calls surface here.
          </Callout>
        ) : report.security_findings.length === 0 ? (
          <Empty>All hops analyzed — nothing tripped.</Empty>
        ) : (
          <div style={{ display: 'flex', flexDirection: 'column', gap: 8 }}>
            {report.security_findings.map((f, i) => (
              <div key={i} style={{ display: 'flex', gap: 10, alignItems: 'baseline', flexWrap: 'wrap' }}>
                <Badge tone={f.action === 'block' ? 'defect' : 'accent'}>{f.action}</Badge>
                <span style={{ ...mono, color: 'var(--ink-2)' }}>{f.hop}</span>
                {f.source && <span style={{ ...mono, color: 'var(--muted)' }}>{f.source}</span>}
                {f.categories.length > 0 && (
                  <span style={{ ...mono, color: 'var(--muted)' }}>— {f.categories.join(', ')}</span>
                )}
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  );
}

/* ---------------- frame ---------------- */

export function Intake() {
  const [form, setForm] = React.useState(BLANK);
  const [discMeta, setDiscMeta] = React.useState('awaiting input');
  const [retrieval, setRetrieval] = React.useState(null);
  const [live, setLive] = React.useState(false);
  const [snap, setSnap] = React.useState(null);
  const [jobId, setJobId] = React.useState(null);
  const [status, setStatus] = React.useState('');
  const [running, setRunning] = React.useState(false);

  // An in-flight poll from a previous job can resolve after a new one starts;
  // without this it would clear the *new* job's timer and render the *old*
  // job's claims as the new run's result.
  const activeJob = React.useRef(null);
  const timer = React.useRef(null);
  const previewTimer = React.useRef(null);
  const formRef = React.useRef(form);
  formRef.current = form;

  const set = (k) => (e) => setForm((f) => ({ ...f, [k]: e.target.value }));

  /* Retrieval is pure BM25 over the corpus — no model call, single-digit ms — so
   * it can run while the inventor types instead of waiting for submit. Watching
   * the matched failure modes change as the disclosure is described is the whole
   * "compares against what it knows" argument, made continuous. */
  const previewContext = React.useCallback(async () => {
    const f = formRef.current;
    if (!f.title && !f.summary && !f.details) return;
    try {
      const r = await api.retrieve(toDisclosure(f));
      setRetrieval(r);
      setLive(true);
    } catch { /* preview is best-effort; the real retrieval runs with the job */ }
  }, []);

  const loadSample = React.useCallback(async () => {
    const d = await api.sample();
    setForm({
      title: d.title,
      technology_class: d.technology_class,
      inventors: d.inventors.join(', '),
      summary: d.summary,
      details: d.details,
    });
    setDiscMeta(`sample · ${d.id}`);
  }, []);

  const poll = React.useCallback(async (id) => {
    try {
      const s = await api.draftStatus(id);
      if (id !== activeJob.current) return;   // a superseded job's response — drop it
      if (s.retrieval) { setRetrieval(s.retrieval); setLive(false); }
      setSnap(s);
      if (s.status === 'done') {
        clearInterval(timer.current);
        setRunning(false);
      } else if (s.status === 'error') {
        clearInterval(timer.current);
        setStatus('Error: ' + s.error);
        setRunning(false);
      }
    } catch (e) {
      if (id !== activeJob.current) return;
      clearInterval(timer.current);
      setStatus('Lost the job: ' + e.message);
      setRunning(false);
    }
  }, []);

  const draft = React.useCallback(async () => {
    clearInterval(timer.current);
    setRunning(true);
    setSnap(null);
    setStatus('Starting…');
    try {
      const { job_id } = await api.startDraft(toDisclosure(formRef.current));
      activeJob.current = job_id;
      setJobId(job_id);
      setStatus('');
      timer.current = setInterval(() => poll(job_id), POLL_MS);
      poll(job_id);
    } catch (e) {
      setStatus('Error: ' + e.message);
      setRunning(false);
    }
  }, [poll]);

  // Debounced live preview as the disclosure is typed.
  React.useEffect(() => {
    clearTimeout(previewTimer.current);
    previewTimer.current = setTimeout(previewContext, PREVIEW_MS);
    return () => clearTimeout(previewTimer.current);
  }, [form.title, form.technology_class, form.summary, form.details, previewContext]);

  // Boot: prefill the sample, then honour `/#autodraft` — it runs the sample
  // straight through on load, for rehearsing the demo without a click.
  React.useEffect(() => {
    let cancelled = false;
    loadSample()
      .then(() => { if (!cancelled && location.hash === '#autodraft') draft(); })
      .catch((e) => setStatus('Could not load the sample: ' + e.message));
    return () => { cancelled = true; clearInterval(timer.current); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  const done = snap && snap.status === 'done';

  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: 40 }}>
      {/* hero */}
      <div style={{ maxWidth: 640 }}>
        <div style={{
          fontFamily: 'var(--font-sans)', fontWeight: 'var(--weight-semibold)',
          fontSize: 'var(--text-sm)', letterSpacing: '0.14em', textTransform: 'uppercase',
          color: 'var(--muted-2)', marginBottom: 14,
        }}>Intake · new disclosure</div>
        <h1 style={{
          margin: 0, fontFamily: 'var(--font-serif)', fontWeight: 400, fontSize: '2.9rem',
          lineHeight: 1.04, letterSpacing: '-0.01em', color: 'var(--ink)',
        }}>Describe your invention.</h1>
        <p style={{ margin: '16px 0 0', fontSize: 'var(--text-lead)', lineHeight: 1.5, color: 'var(--muted)' }}>
          Plain language is enough. Airtight finds the failure modes it has to survive, then drafts the claims.
        </p>
      </div>

      {/* 01 · Disclosure */}
      <section>
        <SectionHead n="01" title="Disclosure" meta={discMeta} />
        <div style={panelCard}>
          <div style={{ display: 'grid', gridTemplateColumns: '1fr 1fr', gap: '22px 24px' }}>
            <TextField label="Title" id="f-title" value={form.title} onChange={set('title')} style={{ gridColumn: '1 / -1' }} />
            <TextField label="Technology class · CPC" id="f-class" placeholder="G06F" value={form.technology_class} onChange={set('technology_class')} />
            <TextField label="Inventors" id="f-inventors" placeholder="comma separated" value={form.inventors} onChange={set('inventors')} />
            <TextArea label="Summary" id="f-summary" rows={3} value={form.summary} onChange={set('summary')} style={{ gridColumn: '1 / -1' }} />
            <TextArea label="Details" id="f-details" rows={6} value={form.details} onChange={set('details')} style={{ gridColumn: '1 / -1' }} />
          </div>
          <div style={{ display: 'flex', gap: 12, alignItems: 'center', marginTop: 26 }}>
            <Button disabled={running} onClick={draft}>Draft patent</Button>
            <Button variant="ghost" onClick={() => loadSample().catch(() => {})}>Load sample</Button>
            <span style={{ fontSize: 'var(--text-body)', color: 'var(--muted)' }}>{status}</span>
          </div>
        </div>
      </section>

      {/* 02 · Context match */}
      <section>
        <SectionHead
          n="02"
          title="Context match"
          meta={retrieval
            ? `${retrieval.selected.length} of ${retrieval.corpus_size} records · k=${retrieval.k}${live ? ' · live' : ''}`
            : '—'}
        />
        <ContextMatch retrieval={retrieval} live={live} />
      </section>

      {/* 03 · Pipeline */}
      <section>
        <SectionHead n="03" title="Pipeline" meta={snap ? `${snap.status} · ${snap.elapsed_s}s` : 'idle'} />
        <Pipeline snap={snap} />
      </section>

      {/* 04 · Grant */}
      {done && (
        <section>
          <SectionHead n="04" title="Grant" meta={`${snap.draft.claims.length} claims · ${snap.elapsed_s}s`} />
          <div style={panelCard}>
            <Grant jobId={jobId} snap={snap} />
          </div>
        </section>
      )}
    </div>
  );
}

const panelCard = {
  background: 'var(--card)',
  border: '1px solid var(--border)',
  borderRadius: 'var(--radius-lg)',
  boxShadow: 'var(--shadow-card)',
  padding: 32,
};

const panelSunk = {
  background: 'rgba(80, 91, 75, 0.05)',
  border: '1px solid rgba(80, 91, 75, 0.16)',
  borderRadius: 'var(--radius-lg)',
  padding: 32,
};

const pipelineIdle = {
  display: 'flex',
  alignItems: 'center',
  gap: 16,
  background: 'var(--forest-wash)',
  borderLeft: '3px solid var(--forest)',
  borderRadius: 'var(--radius-md)',
  padding: '22px 26px',
};

const eyebrowLabel = {
  fontFamily: 'var(--font-sans)',
  fontWeight: 'var(--weight-semibold)',
  fontSize: 'var(--text-sm)',
  letterSpacing: 'var(--tracking-eyebrow)',
  textTransform: 'uppercase',
  color: 'var(--muted-2)',
  marginBottom: 14,
};
