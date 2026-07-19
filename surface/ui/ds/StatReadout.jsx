import React from 'react';

/**
 * A row of compact readouts — the big-number instrument cluster at the top of
 * Airtight panels (e.g. 5 RETRIEVED · 4 STATUTES · 193 CORPUS). Values are set
 * in the display serif; captions are small uppercase sans. Per-item `tone`
 * colours a value (forest by default, defect for a warning figure, ink/muted
 * to recede).
 */
export function StatReadout({ items = [], gap = 40, size = 'md', style, ...rest }) {
  const fs = size === 'lg' ? '3.25rem' : size === 'sm' ? '1.75rem' : '2.25rem';
  const color = (tone) =>
    tone === 'defect' ? 'var(--defect)' :
    tone === 'ink' ? 'var(--ink)' :
    tone === 'muted' ? 'var(--muted-2)' :
    'var(--forest)';
  return (
    <div style={{ display: 'flex', gap, flexWrap: 'wrap', ...style }} {...rest}>
      {items.map((it, i) => (
        <div key={i}>
          <div style={{ fontFamily: 'var(--font-serif)', fontWeight: 'var(--weight-regular)', fontSize: fs, lineHeight: 1, letterSpacing: 'var(--tracking-tight)', color: color(it.tone) }}>{it.value}</div>
          <div style={{ fontFamily: 'var(--font-sans)', fontWeight: 'var(--weight-semibold)', fontSize: 'var(--text-sm)', letterSpacing: 'var(--tracking-eyebrow)', textTransform: 'uppercase', color: 'var(--muted-2)', marginTop: 8 }}>{it.label}</div>
        </div>
      ))}
    </div>
  );
}
