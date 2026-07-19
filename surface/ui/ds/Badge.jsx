import React from 'react';

/**
 * A compact status pill. Pete uses these for pipeline verdicts: a quiet neutral
 * for routine PASS states, the ink "solid" for the one action that stopped the
 * line (QUARANTINE), and small tinted variants for softer flags (REDACT).
 */
export function Badge({ children, tone = 'neutral', solid = false, style, ...rest }) {
  const tones = {
    neutral: { color: 'var(--muted)', background: 'var(--wash)', border: '1px solid transparent' },
    accent:  { color: 'var(--forest-deep)', background: 'var(--forest-wash)', border: '1px solid transparent' },
    ink:     { color: 'var(--on-ink)', background: 'var(--ink-badge)', border: '1px solid var(--ink-badge)' },
    outline: { color: 'var(--muted)', background: 'transparent', border: '1px solid var(--border-strong)' },
    defect:  { color: 'var(--defect)', background: 'var(--defect-wash)', border: '1px solid transparent' },
  };
  const solidMap = {
    neutral: tones.neutral,
    accent:  { color: 'var(--on-primary)', background: 'var(--forest)', border: '1px solid var(--forest)' },
    ink:     tones.ink,
    outline: tones.outline,
    defect:  { color: 'var(--on-defect)', background: 'var(--defect)', border: '1px solid var(--defect)' },
  };
  const chosen = solid ? solidMap[tone] : tones[tone];

  return (
    <span
      style={{
        display: 'inline-flex',
        alignItems: 'center',
        fontFamily: 'var(--font-sans)',
        fontWeight: 'var(--weight-semibold)',
        fontSize: 'var(--text-xs)',
        letterSpacing: 'var(--tracking-tag)',
        textTransform: 'uppercase',
        padding: '0.3rem 0.5rem',
        borderRadius: 'var(--radius-sm)',
        lineHeight: 1,
        whiteSpace: 'nowrap',
        ...chosen,
        ...style,
      }}
      {...rest}
    >
      {children}
    </span>
  );
}
