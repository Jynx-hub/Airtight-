import React from 'react';

/**
 * A labelled horizontal bar for comparisons and mined-record breakdowns. Left
 * label, a bar, and a right-aligned value. With `track` it draws a beige
 * channel behind a green fill; without, the bar is a single colour on the page.
 */
export function Meter({
  label,
  value,
  max = 100,
  tone = 'forest',
  track = true,
  valueLabel,
  emphasizeValue = false,
  barHeight = 22,
  style,
  ...rest
}) {
  const pct = Math.max(0, Math.min(100, (value / max) * 100));
  const fill = tone === 'forest' ? 'var(--forest)' : tone === 'defect' ? 'var(--defect)' : tone === 'muted' ? 'var(--muted-2)' : 'var(--track)';
  return (
    <div style={{ display: 'grid', gridTemplateColumns: 'minmax(56px, auto) 1fr auto', alignItems: 'center', gap: '1rem', ...style }} {...rest}>
      <span style={{ fontFamily: 'var(--font-sans)', fontSize: 'var(--text-body)', color: 'var(--muted)' }}>{label}</span>
      <div style={{ height: barHeight, background: track ? 'var(--track)' : 'transparent', borderRadius: '4px', overflow: 'hidden' }}>
        <div style={{ width: pct + '%', height: '100%', background: fill, borderRadius: '4px', transition: 'width var(--dur-base) var(--ease-standard)' }} />
      </div>
      <span style={{
        fontFamily: 'var(--font-sans)',
        fontSize: 'var(--text-body)',
        fontWeight: emphasizeValue ? 'var(--weight-semibold)' : 'var(--weight-regular)',
        color: emphasizeValue ? 'var(--ink)' : 'var(--muted)',
        minWidth: '2ch',
        textAlign: 'right',
      }}>{valueLabel ?? value}</span>
    </div>
  );
}
