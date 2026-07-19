import React from 'react';

/**
 * A labelled single-line field. The label is a small uppercase sans caption
 * above a warm white input with a hairline border and a green focus ring.
 */
export function TextField({ label, id, hint, style, inputStyle, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', ...style }}>
      {label && (
        <label htmlFor={id} style={labelStyle}>{label}</label>
      )}
      <input
        id={id}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{ ...fieldBase, ...(focus ? fieldFocus : null), ...inputStyle }}
        {...rest}
      />
      {hint && <span style={hintStyle}>{hint}</span>}
    </div>
  );
}

/**
 * A labelled multi-line field, matching TextField. Used for the disclosure
 * summary and details on intake.
 */
export function TextArea({ label, id, hint, rows = 4, style, inputStyle, ...rest }) {
  const [focus, setFocus] = React.useState(false);
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.4rem', ...style }}>
      {label && <label htmlFor={id} style={labelStyle}>{label}</label>}
      <textarea
        id={id}
        rows={rows}
        onFocus={() => setFocus(true)}
        onBlur={() => setFocus(false)}
        style={{ ...fieldBase, resize: 'vertical', lineHeight: 1.55, ...(focus ? fieldFocus : null), ...inputStyle }}
        {...rest}
      />
      {hint && <span style={hintStyle}>{hint}</span>}
    </div>
  );
}

const labelStyle = {
  fontFamily: 'var(--font-sans)',
  fontWeight: 'var(--weight-medium)',
  fontSize: 'var(--text-body)',
  color: 'var(--ink-2)',
};

const fieldBase = {
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-body)',
  color: 'var(--ink)',
  background: 'var(--card)',
  border: '1px solid var(--border-strong)',
  borderRadius: 'var(--radius-md)',
  padding: '0.7rem 0.85rem',
  width: '100%',
  boxSizing: 'border-box',
  outline: 'none',
  transition: 'border-color var(--dur-fast) var(--ease-standard), box-shadow var(--dur-fast) var(--ease-standard)',
};

const fieldFocus = {
  borderColor: 'var(--forest)',
  boxShadow: '0 0 0 3px var(--focus-ring)',
};

const hintStyle = {
  fontFamily: 'var(--font-sans)',
  fontSize: 'var(--text-sm)',
  color: 'var(--muted-2)',
};
