import React from 'react';

/**
 * A warm surface panel. Optionally carries a header row (a title plus a
 * right-aligned meta note) above the body. Two title styles: the default sans
 * heading, or an `eyebrow` kicker for the small uppercase card labels Pete uses
 * over claims and audit blocks.
 */
export function Card({
  title,
  meta,
  eyebrow = false,
  padding = 'var(--gutter-card)',
  sunk = false,
  children,
  style,
  bodyStyle,
  ...rest
}) {
  return (
    <section
      style={{
        background: sunk ? 'var(--surface-sunk)' : 'var(--surface)',
        border: '1px solid var(--border)',
        borderRadius: 'var(--radius-lg)',
        boxShadow: sunk ? 'none' : 'var(--shadow-card)',
        overflow: 'hidden',
        ...style,
      }}
      {...rest}
    >
      {(title || meta) && (
        <header
          style={{
            display: 'flex',
            alignItems: 'baseline',
            justifyContent: 'space-between',
            gap: '1rem',
            padding: `${eyebrow ? '1rem' : '1.1rem'} ${padding} 0`,
          }}
        >
          {title && (
            <h2 style={eyebrow ? eyebrowTitle : cardTitle}>{title}</h2>
          )}
          {meta && <span style={metaStyle}>{meta}</span>}
        </header>
      )}
      <div style={{ padding, ...bodyStyle }}>{children}</div>
    </section>
  );
}

const cardTitle = {
  margin: 0,
  fontFamily: 'var(--font-sans)',
  fontWeight: 'var(--weight-semibold)',
  fontSize: 'var(--text-h2)',
  color: 'var(--ink)',
  lineHeight: 1.3,
};

const eyebrowTitle = {
  margin: 0,
  fontFamily: 'var(--font-sans)',
  fontWeight: 'var(--weight-semibold)',
  fontSize: 'var(--text-sm)',
  letterSpacing: 'var(--tracking-eyebrow)',
  textTransform: 'uppercase',
  color: 'var(--muted-2)',
};

const metaStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-sm)',
  color: 'var(--muted-2)',
  whiteSpace: 'nowrap',
};
