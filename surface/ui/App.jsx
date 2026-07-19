import React from 'react';
import * as api from './api.js';
import { StatusLED } from './ds/index.js';
import { Intake } from './Intake.jsx';
import { Engine } from './Engine.jsx';

/* The two frames share one bundle but not one URL: `/` and `/admin` stay real,
 * server-served, deep-linkable routes (surface/app.py serves a shell for each).
 * The toggle pushes history rather than swapping state alone, so a hard reload
 * or a shared link lands on the same frame. */

const pathFor = (view) => (view === 'engine' ? '/admin' : '/');
const viewFor = (path) => (path.replace(/\/+$/, '') === '/admin' ? 'engine' : 'intake');

function TopBar({ view, onSelect, leds }) {
  return (
    <header style={{
      position: 'sticky', top: 0, zIndex: 20,
      display: 'flex', alignItems: 'center', gap: 28,
      padding: '0 32px', minHeight: 60, flexWrap: 'wrap',
      background: 'var(--bg-raised)', borderBottom: '1px solid var(--border)',
    }}>
      <div style={{ display: 'flex', alignItems: 'center', gap: 12 }}>
        <span style={{ width: 11, height: 11, background: 'var(--forest)', borderRadius: 2, display: 'inline-block' }} />
        <span style={{ fontWeight: 'var(--weight-bold)', fontSize: 'var(--text-body)', letterSpacing: '0.16em', color: 'var(--ink)' }}>
          AIRTIGHT
        </span>
        <span style={{ color: 'var(--faint)' }}>/</span>
        <span style={{
          fontWeight: 'var(--weight-semibold)', fontSize: 'var(--text-sm)',
          letterSpacing: 'var(--tracking-eyebrow)', textTransform: 'uppercase', color: 'var(--muted-2)',
        }}>
          {view === 'engine' ? 'Engine' : 'Intake'}
        </span>
      </div>

      <div style={{ display: 'flex', gap: 20, flexWrap: 'wrap' }}>
        {leds.map((l) => <StatusLED key={l.label} label={l.label} value={l.value} state={l.state} />)}
      </div>

      <nav style={{ marginLeft: 'auto', display: 'flex', gap: 8 }}>
        {[['intake', 'Intake'], ['engine', 'Engine']].map(([id, label]) => {
          const active = view === id;
          return (
            <a
              key={id}
              href={pathFor(id)}
              aria-current={active ? 'page' : undefined}
              onClick={(e) => {
                // Plain click navigates in-page; modified clicks (new tab, etc.)
                // fall through to the browser so the href stays honest.
                if (e.metaKey || e.ctrlKey || e.shiftKey || e.altKey || e.button !== 0) return;
                e.preventDefault();
                onSelect(id);
              }}
              style={{
                fontFamily: 'var(--font-sans)', fontWeight: 'var(--weight-semibold)',
                fontSize: 'var(--text-sm)', letterSpacing: '0.1em', textTransform: 'uppercase',
                padding: '0.5rem 0.9rem', borderRadius: 'var(--radius-md)', cursor: 'pointer',
                textDecoration: 'none',
                color: active ? 'var(--forest-deep)' : 'var(--muted)',
                background: active ? 'var(--forest-wash)' : 'transparent',
                border: active ? '1px solid var(--forest-deep)' : '1px solid var(--border-strong)',
              }}
            >{label}</a>
          );
        })}
      </nav>
    </header>
  );
}

export function App({ initialView }) {
  const [view, setView] = React.useState(initialView || viewFor(location.pathname));
  const [health, setHealth] = React.useState(null);
  const [healthFailed, setHealthFailed] = React.useState(false);
  const [panelLeds, setPanelLeds] = React.useState({});

  const onLed = React.useCallback((led) => {
    setPanelLeds((prev) => (
      prev[led.label]?.value === led.value && prev[led.label]?.state === led.state
        ? prev
        : { ...prev, [led.label]: led }
    ));
  }, []);

  React.useEffect(() => {
    api.health().then(setHealth).catch(() => setHealthFailed(true));
  }, []);

  // Back/forward must move between frames, not just change the address bar.
  React.useEffect(() => {
    const onPop = () => setView(viewFor(location.pathname));
    window.addEventListener('popstate', onPop);
    return () => window.removeEventListener('popstate', onPop);
  }, []);

  const go = (next) => {
    if (next === view) return;
    history.pushState({ view: next }, '', pathFor(next) + location.hash);
    setView(next);
    const el = document.getElementById('at-scroll');
    if (el) el.scrollTop = 0;
  };

  const mode = healthFailed
    ? { label: 'MODE', value: 'offline', state: 'alert' }
    : { label: 'MODE', value: health?.mode ?? '…', state: health?.mode === 'live' ? 'on' : 'off' };

  const leds = view === 'engine'
    ? [
        mode,
        panelLeds.CORPUS ?? { label: 'CORPUS', value: '…', state: 'muted' },
        panelLeds.BUS ?? { label: 'BUS', value: '…', state: 'muted' },
      ]
    : [
        mode,
        { label: 'MODEL', value: health ? String(health.model).split('/').pop() : '…', state: health ? 'on' : 'muted' },
        { label: 'HIDDENLAYER', value: health ? (health.hl_enabled ? 'on' : 'off') : '…', state: health?.hl_enabled ? 'on' : 'off' },
      ];

  return (
    <div style={{ height: '100vh', display: 'flex', flexDirection: 'column', background: 'var(--bg)' }}>
      <TopBar view={view} onSelect={go} leds={leds} />
      <div id="at-scroll" style={{ flex: 1, overflowY: 'auto' }}>
        <div style={{ maxWidth: 'var(--content-max)', margin: '0 auto', padding: '28px 32px 80px' }}>
          {view === 'engine' ? <Engine onLed={onLed} /> : <Intake />}
        </div>
      </div>
    </div>
  );
}
