"""Side-by-side ablation chart: self-contained HTML + inline SVG, stdlib only.

results.json stays the canonical output (Person 3's D5 view consumes it); this
file is the zero-dependency fallback that opens in any browser. Styling follows
the dataviz reference palette (series 1/2 = blue/aqua, both modes validated).
"""

import json
from pathlib import Path
from statistics import mean

PANELS = [
    ("loopholes_caught", "Loopholes caught", "higher is better"),
    ("drafting_seconds", "Wall-clock per draft (s)", "lower is better"),
    ("defect_count", "Defects (judge rubric)", "lower is better"),
]
CONDITIONS = ("empty", "warmed")  # fixed series order — never cycled

W, H, PAD_TOP, PAD_BOTTOM, BAR_W, GAP = 220, 190, 34, 30, 56, 2


def _bar(x: float, y: float, w: float, h: float, cls: str, tip: str) -> str:
    if h < 0.5:  # zero-height mark: baseline tick only, label still shown
        return ""
    r = min(4.0, h)  # 4px rounded data-end, anchored flat to the baseline
    return (
        f'<path class="bar {cls}" d="M{x},{y + h} v-{h - r} q0,-{r} {r},-{r} h{w - 2 * r} '
        f'q{r},0 {r},{r} v{h - r} z"><title>{tip}</title></path>'
    )


def _fmt(v: float) -> str:
    return f"{round(v, 1):g}"  # 7 -> "7", 7.5 -> "7.5" — means stay honest


def _panel(title: str, direction: str, values: dict[str, float]) -> str:
    top = max(max(values.values()), 1e-9) * 1.15
    base_y = H - PAD_BOTTOM
    plot_h = base_y - PAD_TOP
    group_w = BAR_W * 2 + GAP
    x0 = (W - group_w) / 2

    bars, labels = [], []
    for i, cond in enumerate(CONDITIONS):
        v = values[cond]
        h = plot_h * v / top
        x = x0 + i * (BAR_W + GAP)
        bars.append(_bar(x, base_y - h, BAR_W, h, cond, f"{cond}: {_fmt(v)}"))
        labels.append(
            f'<text class="val" x="{x + BAR_W / 2}" y="{base_y - h - 6}">{_fmt(v)}</text>'
            f'<text class="cond" x="{x + BAR_W / 2}" y="{base_y + 16}">{cond}</text>'
        )
    return f"""
  <figure>
    <figcaption>{title} <span class="dir">({direction})</span></figcaption>
    <svg viewBox="0 0 {W} {H}" role="img" aria-label="{title}, empty vs warmed">
      <line class="baseline" x1="8" y1="{base_y}" x2="{W - 8}" y2="{base_y}"/>
      {''.join(bars)}
      {''.join(labels)}
    </svg>
  </figure>"""


def write_chart(results_json: Path, out_html: Path) -> None:
    payload = json.loads(Path(results_json).read_text())
    results = payload["results"]
    fp = payload["fingerprint"]

    means = {
        key: {c: mean([r[key] for r in results if r["condition"] == c] or [0]) for c in CONDITIONS}
        for key, _, _ in PANELS
    }
    checklist_note = f" of {results[0]['checklist_size']}" if results else ""

    panels = "".join(
        _panel(title + (checklist_note if key == "loopholes_caught" else ""), direction, means[key])
        for key, title, direction in PANELS
    )

    rows = "".join(
        f"<tr><td>{p['disclosure_id']}</td>"
        f"<td>{p['loopholes_caught_delta']:+d}</td>"
        f"<td>{p['drafting_seconds_delta']:+.1f}s</td>"
        f"<td>{p['defect_count_delta']:+d}</td></tr>"
        for p in payload["pairs"]
    )

    stub_banner = (
        '<p class="stub">STUB MODE — plumbing check; no delta expected. Run with '
        "AIRTIGHT_MODE=live for the real ablation.</p>"
        if fp["mode"] == "stub"
        else ""
    )

    html = f"""<!doctype html>
<meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Airtight M4 ablation — empty vs warmed</title>
<style>
  .viz-root {{
    --surface: #fcfcfb; --ink: #0b0b0b; --ink-2: #52514e; --muted: #898781;
    --baseline: #c3c2b7; --series-empty: #2a78d6; --series-warmed: #1baf7a;
    background: var(--surface); color: var(--ink); max-width: 760px; margin: 2rem auto;
    padding: 1.5rem; font-family: system-ui, -apple-system, "Segoe UI", sans-serif;
  }}
  @media (prefers-color-scheme: dark) {{
    .viz-root {{
      --surface: #1a1a19; --ink: #ffffff; --ink-2: #c3c2b7; --muted: #898781;
      --baseline: #383835; --series-empty: #3987e5; --series-warmed: #199e70;
    }}
  }}
  h1 {{ font-size: 1.1rem; margin: 0 0 .25rem; }}
  .legend {{ display: flex; gap: 1.25rem; margin: .5rem 0 1rem; font-size: .85rem; color: var(--ink-2); }}
  .legend i {{ display: inline-block; width: 12px; height: 12px; border-radius: 3px; margin-right: 6px; vertical-align: -1px; }}
  .panels {{ display: flex; flex-wrap: wrap; gap: .5rem; }}
  figure {{ margin: 0; flex: 1 1 200px; }}
  figcaption {{ font-size: .85rem; color: var(--ink-2); text-align: center; }}
  .dir {{ color: var(--muted); font-size: .75rem; }}
  .bar.empty {{ fill: var(--series-empty); }}
  .bar.warmed {{ fill: var(--series-warmed); }}
  .bar:hover {{ filter: brightness(1.12); }}
  .baseline {{ stroke: var(--baseline); stroke-width: 1; }}
  .val {{ fill: var(--ink); font-size: 12px; text-anchor: middle; }}
  .cond {{ fill: var(--ink-2); font-size: 11px; text-anchor: middle; }}
  .stub {{ color: var(--ink-2); border: 1px solid var(--baseline); border-radius: 6px; padding: .5rem .75rem; font-size: .85rem; }}
  table {{ border-collapse: collapse; font-size: .85rem; margin-top: 1rem; }}
  th, td {{ padding: .3rem .75rem; text-align: left; border-bottom: 1px solid var(--baseline); font-variant-numeric: tabular-nums; }}
  th {{ color: var(--ink-2); font-weight: 600; }}
  footer {{ color: var(--muted); font-size: .75rem; margin-top: 1.25rem; line-height: 1.5; }}
</style>
<div class="viz-root">
  <h1>M4 ablation — same model, same prompts, only the memory differs</h1>
  <div class="legend">
    <span><i style="background:var(--series-empty)"></i>empty memory</span>
    <span><i style="background:var(--series-warmed)"></i>warmed on {payload["corpus_size"]} records</span>
  </div>
  {stub_banner}
  <div class="panels">{panels}</div>
  <table>
    <tr><th>disclosure</th><th>Δ loopholes</th><th>Δ time</th><th>Δ defects</th></tr>
    {rows}
  </table>
  <footer>
    {fp["timestamp"]} · mode={fp["mode"]} · model={fp["model"]} · host={fp["base_url_host"]}
    · k={fp["k"]} · runs={fp["runs"]} · git={fp["git_sha"][:10]}<br>
    draft gen={json.dumps(fp["draft_gen"])} · judge gen={json.dumps(fp["judge_gen"])}
    · prompt hashes in results.json — nothing else changed between conditions.
  </footer>
</div>
"""
    Path(out_html).write_text(html)
