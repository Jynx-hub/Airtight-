import React from 'react';

/* The corpus as a force-directed topology: statute hubs on the left arc, CPC
 * class hubs on the right, one record node per mined record wired to both.
 *
 * Every count here comes from /api/memory/stats — the node population is the
 * real corpus, not a sample. Record nodes are capped at MAX_NODES for frame
 * rate; when the cap bites, the legend says so rather than implying the whole
 * corpus is on screen. */

const MAX_NODES = 220;

const C = {
  graphBg: '#F4F2EC',
  link: '#E1DBCC',
  linkHi: '#505B4B',
  statute: '#37342B',
  cpc: '#928B79',
  record: '#93A07F',
  label: '#37342B',
  labelMuted: '#8B8270',
};

/* A tiny seeded RNG so the layout is stable across renders. */
function mulberry32(a) {
  return function () {
    a |= 0; a = (a + 0x6D2B79F5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function buildGraph(byStatute, byClass) {
  const rnd = mulberry32(20260718);
  const statutes = Object.entries(byStatute).sort((a, b) => b[1] - a[1]);
  const cpcs = Object.entries(byClass).sort((a, b) => b[1] - a[1]);
  const nodes = [];
  const links = [];

  if (!statutes.length || !cpcs.length) return { nodes, links, shown: 0 };

  const arc = (i, n, base, spread) => Math.PI * (base + spread * (n === 1 ? 0.5 : i / (n - 1)));

  statutes.forEach(([id], i) => {
    const a = arc(i, statutes.length, 0.62, 0.52);
    nodes.push({
      id: `§${id}`, type: 'statute', r: 11, label: `§${id}`,
      ax: 0.30 + 0.16 * Math.cos(a), ay: 0.5 + 0.42 * Math.sin(a),
    });
  });
  cpcs.forEach(([id], i) => {
    const a = arc(i, cpcs.length, 1.62, 0.5);
    nodes.push({
      id, type: 'cpc', r: 10, label: id,
      ax: 0.74 + 0.15 * Math.cos(a), ay: 0.5 + 0.4 * Math.sin(a),
    });
  });

  // Records are drawn proportional to the real per-statute mass, scaled down
  // together when the corpus is larger than the node cap.
  const total = statutes.reduce((a, [, v]) => a + v, 0);
  const scale = total > MAX_NODES ? MAX_NODES / total : 1;
  const cpcTotal = cpcs.reduce((a, [, v]) => a + v, 0);
  const cpcPick = () => {
    let r = rnd() * cpcTotal;
    for (const [id, w] of cpcs) if ((r -= w) <= 0) return id;
    return cpcs[0][0];
  };

  let ri = 0;
  statutes.forEach(([sid, count]) => {
    const n = Math.max(1, Math.round(count * scale));
    for (let k = 0; k < n; k++) {
      const id = 'r' + ri++;
      const cpc = cpcPick();
      nodes.push({ id, type: 'record', r: 3.6, label: `§${sid} · ${cpc}` });
      links.push({ s: id, t: `§${sid}` });
      links.push({ s: id, t: cpc });
    }
  });

  return { nodes, links, shown: ri, capped: total > MAX_NODES };
}

export function CorpusGraph({ byStatute, byClass, height = 420 }) {
  const wrapRef = React.useRef(null);
  const canvasRef = React.useRef(null);
  const [hoverLabel, setHoverLabel] = React.useState(null);
  const [meta, setMeta] = React.useState({ shown: 0, capped: false });

  React.useEffect(() => {
    const wrap = wrapRef.current, canvas = canvasRef.current;
    if (!wrap || !canvas) return;
    const ctx = canvas.getContext('2d');
    const { nodes, links, shown, capped } = buildGraph(byStatute, byClass);
    setMeta({ shown, capped });
    if (!nodes.length) return;

    const byId = Object.fromEntries(nodes.map((n) => [n.id, n]));
    const nbr = {};
    nodes.forEach((n) => (nbr[n.id] = new Set()));
    links.forEach((l) => { nbr[l.s].add(l.t); nbr[l.t].add(l.s); });

    let W = 0, H = height;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    const view = { x: 0, y: 0, k: 1 };
    let hover = null, drag = null, panning = null;

    function resize() {
      W = wrap.clientWidth;
      canvas.width = W * dpr; canvas.height = H * dpr;
      canvas.style.width = W + 'px'; canvas.style.height = H + 'px';
    }
    resize();

    const rnd = mulberry32(7);
    nodes.forEach((n) => {
      n.x = (n.ax != null ? n.ax : 0.2 + 0.6 * rnd()) * W + (rnd() - 0.5) * 40;
      n.y = (n.ay != null ? n.ay : 0.2 + 0.6 * rnd()) * H + (rnd() - 0.5) * 40;
      n.vx = 0; n.vy = 0;
    });

    function tick() {
      for (let i = 0; i < nodes.length; i++) {
        const a = nodes[i];
        for (let j = i + 1; j < nodes.length; j++) {
          const b = nodes[j];
          const dx = a.x - b.x, dy = a.y - b.y;
          const d2 = dx * dx + dy * dy || 0.01;
          const f = 520 / d2;
          const d = Math.sqrt(d2);
          const ux = dx / d, uy = dy / d;
          a.vx += ux * f; a.vy += uy * f; b.vx -= ux * f; b.vy -= uy * f;
        }
      }
      for (const l of links) {
        const a = byId[l.s], b = byId[l.t];
        const rest = 56;
        const dx = b.x - a.x, dy = b.y - a.y;
        const d = Math.sqrt(dx * dx + dy * dy) || 0.01;
        const f = (d - rest) * 0.015;
        const ux = dx / d, uy = dy / d;
        a.vx += ux * f; a.vy += uy * f; b.vx -= ux * f; b.vy -= uy * f;
      }
      for (const n of nodes) {
        if (n.ax != null) {
          n.vx += (n.ax * W - n.x) * 0.05;
          n.vy += (n.ay * H - n.y) * 0.05;
        } else {
          n.vx += (W / 2 - n.x) * 0.002;
          n.vy += (H / 2 - n.y) * 0.002;
        }
        if (drag === n) continue;
        n.vx *= 0.82; n.vy *= 0.82;
        n.x += Math.max(-6, Math.min(6, n.vx));
        n.y += Math.max(-6, Math.min(6, n.vy));
      }
    }

    function draw() {
      ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
      ctx.clearRect(0, 0, W, H);
      ctx.save();
      ctx.translate(view.x, view.y);
      ctx.scale(view.k, view.k);
      const active = hover ? nbr[hover.id] : null;

      for (const l of links) {
        const a = byId[l.s], b = byId[l.t];
        const on = hover && (l.s === hover.id || l.t === hover.id);
        ctx.strokeStyle = on ? C.linkHi : C.link;
        ctx.globalAlpha = hover ? (on ? 0.9 : 0.25) : 0.5;
        ctx.lineWidth = (on ? 1.4 : 0.8) / view.k;
        ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.lineTo(b.x, b.y); ctx.stroke();
      }
      ctx.globalAlpha = 1;

      for (const n of nodes) {
        const dim = hover && n !== hover && !active.has(n.id);
        ctx.globalAlpha = dim ? 0.28 : 1;
        ctx.fillStyle = n.type === 'statute' ? C.statute : n.type === 'cpc' ? C.cpc : C.record;
        ctx.beginPath(); ctx.arc(n.x, n.y, n.r, 0, Math.PI * 2); ctx.fill();
      }
      ctx.globalAlpha = 1;

      ctx.textAlign = 'center'; ctx.textBaseline = 'middle';
      for (const n of nodes) {
        if (n.type === 'record' && n !== hover) continue;
        if (hover && n !== hover && !active.has(n.id)) continue;
        ctx.font = `${n.type === 'record' ? 10 : 11.5}px ui-monospace, Menlo, monospace`;
        ctx.fillStyle = n.type === 'record' ? C.labelMuted : C.label;
        ctx.save();
        ctx.translate(n.x, n.y + n.r + 9 / view.k);
        ctx.scale(1 / view.k, 1 / view.k);
        ctx.fillText(n.label, 0, 0);
        ctx.restore();
      }
      ctx.restore();
    }

    let raf;
    const loop = () => { tick(); draw(); raf = requestAnimationFrame(loop); };
    loop();

    const toGraph = (e) => {
      const rect = canvas.getBoundingClientRect();
      return { x: (e.clientX - rect.left - view.x) / view.k, y: (e.clientY - rect.top - view.y) / view.k };
    };
    const pick = (p) => {
      let best = null, bd = 1e9;
      for (const n of nodes) {
        const dx = n.x - p.x, dy = n.y - p.y, d = dx * dx + dy * dy;
        if (d < bd && d < (n.r + 6) ** 2) { bd = d; best = n; }
      }
      return best;
    };
    const onMove = (e) => {
      const p = toGraph(e);
      if (drag) { drag.x = p.x; drag.y = p.y; drag.vx = 0; drag.vy = 0; return; }
      if (panning) { view.x = e.clientX - panning.x; view.y = e.clientY - panning.y; return; }
      hover = pick(p);
      canvas.style.cursor = hover ? 'grab' : 'default';
      setHoverLabel(hover ? hover.label : null);
    };
    const onDown = (e) => {
      const n = pick(toGraph(e));
      if (n) { drag = n; canvas.style.cursor = 'grabbing'; }
      else { panning = { x: e.clientX - view.x, y: e.clientY - view.y }; }
    };
    const onUp = () => { drag = null; panning = null; canvas.style.cursor = 'default'; };
    const onWheel = (e) => {
      e.preventDefault();
      const rect = canvas.getBoundingClientRect();
      const mx = e.clientX - rect.left, my = e.clientY - rect.top;
      const k2 = Math.max(0.5, Math.min(2.4, view.k * (e.deltaY < 0 ? 1.1 : 0.9)));
      view.x = mx - (mx - view.x) * (k2 / view.k);
      view.y = my - (my - view.y) * (k2 / view.k);
      view.k = k2;
    };

    canvas.addEventListener('mousemove', onMove);
    canvas.addEventListener('mousedown', onDown);
    window.addEventListener('mouseup', onUp);
    canvas.addEventListener('wheel', onWheel, { passive: false });
    const ro = new ResizeObserver(resize);
    ro.observe(wrap);

    return () => {
      cancelAnimationFrame(raf);
      ro.disconnect();
      canvas.removeEventListener('mousemove', onMove);
      canvas.removeEventListener('mousedown', onDown);
      window.removeEventListener('mouseup', onUp);
      canvas.removeEventListener('wheel', onWheel);
    };
  }, [byStatute, byClass, height]);

  const Dot = ({ c }) => (
    <span style={{ width: 9, height: 9, borderRadius: '50%', background: c, display: 'inline-block' }} />
  );

  return (
    <>
      <div ref={wrapRef} style={{
        position: 'relative', height, background: C.graphBg,
        border: '1px solid var(--border)', borderRadius: 'var(--radius-md)', overflow: 'hidden',
      }}>
        <canvas ref={canvasRef} style={{ display: 'block' }} />
        {/* Record nodes drift to the bottom of the canvas, so the hint needs its
            own ground to stay legible over them. */}
        <div style={{
          position: 'absolute', left: 10, bottom: 8, fontFamily: 'var(--font-mono)',
          fontSize: 'var(--text-sm)', color: 'var(--muted-2)',
          background: 'rgba(244, 242, 236, 0.88)', padding: '3px 8px',
          borderRadius: 'var(--radius-sm)', pointerEvents: 'none',
        }}>
          {hoverLabel || 'drag nodes · scroll to zoom · hover to trace links'}
        </div>
      </div>
      <div style={{
        display: 'flex', gap: 20, flexWrap: 'wrap', marginTop: 14,
        fontFamily: 'var(--font-sans)', fontSize: 'var(--text-sm)', color: 'var(--muted)',
      }}>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}><Dot c={C.statute} /> statute</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}><Dot c={C.cpc} /> CPC class</span>
        <span style={{ display: 'flex', alignItems: 'center', gap: 7 }}><Dot c={C.record} /> record</span>
        {meta.capped && (
          <span style={{ color: 'var(--muted-2)' }}>
            showing {meta.shown} of the corpus — node count capped for frame rate
          </span>
        )}
      </div>
    </>
  );
}
