import React from 'react';
import { Callout } from './ds/index.js';

/* Shared pieces both frames use. The seam renderer is the important one — see
 * the "Seams" house rule in surface/README.md: anything not yet real renders a
 * badge naming the exact path or command that fills it. If it looks done, it
 * must be done, or it must say plainly that it isn't. */

/**
 * The honesty badge. `sources.py` hands back {seam, label, detail, source} for
 * every artifact that is missing, stale, or synthetic; this is the only thing
 * that renders one, so a seam can never be quietly dropped.
 */
export function Seam({ seam, style }) {
  if (!seam) return null;
  return (
    <Callout variant="dashed" label={seam.label} footer={seam.source} style={style}>
      {seam.detail}
    </Callout>
  );
}

/** A plain explanatory aside — the old `.note`. Defect tone means a warning. */
export function Note({ tone, children, style }) {
  return <Callout tone={tone} style={style}>{children}</Callout>;
}

/** The numbered section header on intake: 01 · Disclosure. */
export function SectionHead({ n, title, meta }) {
  return (
    <div style={{ display: 'flex', alignItems: 'center', gap: 14, marginBottom: 18 }}>
      <span style={{
        display: 'inline-flex', alignItems: 'center', justifyContent: 'center',
        width: 38, height: 38, borderRadius: 11, background: 'var(--forest)',
        color: 'var(--on-forest)', fontFamily: 'var(--font-mono)', fontSize: '0.95rem',
        fontWeight: 700, flex: 'none',
      }}>{n}</span>
      <h2 style={{
        margin: 0, fontFamily: 'var(--font-serif)', fontWeight: 500, fontSize: '1.6rem',
        letterSpacing: '-0.01em', color: 'var(--ink)',
      }}>{title}</h2>
      {meta && (
        <span style={{
          marginLeft: 'auto', fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-sm)', color: 'var(--muted-2)',
        }}>{meta}</span>
      )}
    </div>
  );
}

/** A small uppercase sub-label inside a card body. */
export function SubLabel({ children, style }) {
  return (
    <div style={{
      fontFamily: 'var(--font-sans)', fontWeight: 'var(--weight-semibold)',
      fontSize: 'var(--text-body)', color: 'var(--ink)', margin: '4px 0 14px', ...style,
    }}>{children}</div>
  );
}

/** Placeholder copy — italic serif, the design's quiet empty state. */
export function Empty({ children, pulsing }) {
  return (
    <p className={pulsing ? 'pulsing' : undefined} style={{
      margin: 0, fontFamily: 'var(--font-serif)', fontStyle: 'italic',
      fontSize: 'var(--text-lead)', lineHeight: 1.5, color: 'var(--muted-2)',
    }}>{children}</p>
  );
}

/** Shared table header cell style — hairline rule, tracked uppercase caption. */
export const th = {
  textAlign: 'left',
  fontFamily: 'var(--font-sans)',
  fontWeight: 'var(--weight-semibold)',
  fontSize: 'var(--text-sm)',
  letterSpacing: 'var(--tracking-eyebrow)',
  textTransform: 'uppercase',
  color: 'var(--muted-2)',
  padding: '0 14px 12px',
  borderBottom: '1px solid var(--border-strong)',
};

export const mono = { fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)' };

/** Row separation is a single hairline, never a filled zebra. */
export const rowRule = (isLast) => (isLast ? 'none' : '1px solid var(--border)');

/**
 * Load once on mount. Panels load independently so one bad artifact can't blank
 * the page — the same guarantee admin.js got from its per-panel `.catch()`.
 */
export function useLoad(fn, deps = []) {
  const [state, setState] = React.useState({ loading: true, data: null, error: null });
  React.useEffect(() => {
    let live = true;
    setState((s) => ({ ...s, loading: true }));
    fn()
      .then((data) => live && setState({ loading: false, data, error: null }))
      .catch((error) => live && setState({ loading: false, data: null, error }));
    return () => { live = false; };
  }, deps);
  return state;
}

/** Wraps a panel body so a failed fetch shows the reason instead of nothing. */
export function PanelBody({ loading, error, children, what }) {
  if (loading) return <Empty pulsing>loading…</Empty>;
  if (error) {
    return (
      <Callout tone="defect" label="Panel failed to load" footer={String(error.message || error)}>
        {what} could not be read. The other panels are unaffected.
      </Callout>
    );
  }
  return children;
}

/** Horizontal comparison bar used by the corpus facets and the ablation arms. */
export function Bar({ label, value, max, tone = 'forest', width = 58 }) {
  const fill = tone === 'forest' ? 'var(--forest)'
    : tone === 'defect' ? 'var(--defect)'
    : tone === 'deep' ? 'var(--forest-deep)'
    : 'var(--muted-2)';
  const pct = max ? Math.max(value > 0 ? 4 : 0, (value / max) * 100) : 0;
  return (
    <div style={{ display: 'grid', gridTemplateColumns: `${width}px 1fr 34px`, alignItems: 'center', gap: 12 }}>
      <span style={{ ...mono, color: 'var(--muted)' }}>{label}</span>
      <div style={{ height: 8, background: 'var(--track)', borderRadius: 3, overflow: 'hidden' }}>
        <div style={{ width: pct + '%', height: '100%', background: fill, transition: 'width var(--dur-base) var(--ease-standard)' }} />
      </div>
      <span style={{ ...mono, color: 'var(--muted-2)', textAlign: 'right' }}>{value}</span>
    </div>
  );
}
