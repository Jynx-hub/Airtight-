import React from 'react';

/**
 * A quiet inline note. Two shapes: `bar` (a left-rule aside, Airtight's default
 * for a caveat or explanation) and `dashed` (a hatched, dashed-border panel for
 * "not populated / superseded / incomplete" empty-states). Tone colours the
 * rule and label: `accent` (forest) for neutral notes, `defect` (brick) for
 * warnings that mean something was blocked or is untrustworthy.
 */
export function Callout({ tone = 'accent', variant = 'bar', label, footer, children, style, ...rest }) {
  const rule = tone === 'defect' ? 'var(--defect)' : tone === 'neutral' ? 'var(--border-strong)' : 'var(--forest-deep)';
  const labelColor = tone === 'defect' ? 'var(--defect)' : tone === 'neutral' ? 'var(--muted-2)' : 'var(--forest-deep)';

  const Label = label ? (
    <div style={{ fontFamily: 'var(--font-sans)', fontWeight: 'var(--weight-semibold)', fontSize: 'var(--text-sm)', letterSpacing: 'var(--tracking-eyebrow)', textTransform: 'uppercase', color: labelColor, marginBottom: 10 }}>{label}</div>
  ) : null;

  const Body = <div style={{ fontFamily: 'var(--font-sans)', fontSize: 'var(--text-body)', lineHeight: 1.55, color: 'var(--muted)', textWrap: 'pretty' }}>{children}</div>;

  const Footer = footer ? (
    <div style={{ fontFamily: 'var(--font-mono)', fontSize: 'var(--text-sm)', color: 'var(--muted-2)', marginTop: 14, wordBreak: 'break-word' }}>→ {footer}</div>
  ) : null;

  if (variant === 'dashed') {
    return (
      <div style={{
        border: '1px dashed var(--border-strong)',
        borderRadius: 'var(--radius-md)',
        padding: '16px 18px',
        background: 'repeating-linear-gradient(45deg, transparent, transparent 7px, rgba(80,91,75,0.028) 7px, rgba(80,91,75,0.028) 14px)',
        ...style,
      }} {...rest}>
        {Label}{Body}{Footer}
      </div>
    );
  }
  return (
    <div style={{ borderLeft: `2px solid ${rule}`, paddingLeft: 16, ...style }} {...rest}>
      {Label}{Body}{Footer}
    </div>
  );
}
