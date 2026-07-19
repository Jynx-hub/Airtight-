import React from 'react';

/**
 * Pete's primary action control. Sentence-case sans on a quiet forest fill;
 * the ghost variant drops to a bordered text button for secondary actions.
 */
export function Button({
  children,
  variant = 'primary',
  size = 'md',
  disabled = false,
  type = 'button',
  onClick,
  style,
  ...rest
}) {
  const pad = size === 'sm' ? '0.5rem 0.85rem' : size === 'lg' ? '0.85rem 1.5rem' : '0.7rem 1.15rem';
  const fs = size === 'sm' ? '0.875rem' : size === 'lg' ? '1.0625rem' : 'var(--text-body)';

  const base = {
    display: 'inline-flex',
    alignItems: 'center',
    justifyContent: 'center',
    gap: '0.5rem',
    fontFamily: 'var(--font-sans)',
    fontWeight: 'var(--weight-semibold)',
    fontSize: fs,
    lineHeight: 1.1,
    letterSpacing: '0',
    padding: pad,
    borderRadius: 'var(--radius-md)',
    cursor: disabled ? 'default' : 'pointer',
    opacity: disabled ? 0.45 : 1,
    transition: 'background var(--dur-fast) var(--ease-standard), color var(--dur-fast) var(--ease-standard)',
    whiteSpace: 'nowrap',
    border: '1px solid transparent',
  };

  const variants = {
    primary: { background: 'var(--primary)', color: 'var(--on-primary)', borderColor: 'var(--primary)' },
    ghost:   { background: 'transparent', color: 'var(--primary)', borderColor: 'var(--border-strong)' },
    quiet:   { background: 'transparent', color: 'var(--muted)', borderColor: 'transparent' },
  };

  const [hover, setHover] = React.useState(false);
  const hoverStyle = !disabled && hover
    ? (variant === 'primary'
        ? { background: 'var(--primary-hover)', borderColor: 'var(--primary-hover)' }
        : variant === 'ghost'
          ? { background: 'var(--primary-wash)' }
          : { color: 'var(--ink)', background: 'var(--wash)' })
    : null;

  return (
    <button
      type={type}
      disabled={disabled}
      onClick={onClick}
      onMouseEnter={() => setHover(true)}
      onMouseLeave={() => setHover(false)}
      style={{ ...base, ...variants[variant], ...hoverStyle, ...style }}
      {...rest}
    >
      {children}
    </button>
  );
}
