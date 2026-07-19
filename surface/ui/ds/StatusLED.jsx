import React from 'react';

/**
 * A status LED — a small dot plus a mono label and optional bold value. Used in
 * the Airtight top bar (MODE stub · MODEL … · HIDDENLAYER off) and as a legend
 * marker. `on` glows forest, `alert` glows defect, `off`/`muted` stay grey.
 */
export function StatusLED({ label, value, state = 'muted', style, ...rest }) {
  const color = state === 'on' ? 'var(--forest)' : state === 'alert' ? 'var(--defect)' : 'var(--muted-2)';
  const glow = state === 'on' ? '0 0 6px var(--forest)' : state === 'alert' ? '0 0 6px var(--defect)' : 'none';
  return (
    <span style={{ display: 'inline-flex', alignItems: 'center', gap: '0.45rem', fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--muted)', whiteSpace: 'nowrap', ...style }} {...rest}>
      <span style={{ width: 7, height: 7, borderRadius: '50%', background: color, boxShadow: glow, flex: 'none' }} />
      {label}
      {value != null && <b style={{ color: 'var(--ink-2)', fontWeight: 'var(--weight-semibold)' }}>{value}</b>}
    </span>
  );
}
