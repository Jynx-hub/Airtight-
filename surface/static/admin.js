/* Retired — the engine frame is now surface/ui/Engine.jsx, compiled into
 * static/airtight-kit.js by surface/build.sh.
 *
 * This file is deliberately kept rather than deleted: `test_static_assets_are_mounted`
 * in tests/test_surface.py asserts /static/admin.js returns 200, and that test
 * is what guards the StaticFiles mount the whole surface depends on. Nothing
 * loads this script — both shells load airtight-kit.js instead.
 *
 * Everything it used to do lives on, panel for panel:
 *   corpus facets + learning      → Engine.jsx  <CorpusPanel/> <LearnedPanel/>
 *   retrieval inspector           → Engine.jsx  <InspectorPanel/>
 *   corpus browser + filters      → Engine.jsx  <FailureLibrary/>   (250ms debounce)
 *   ablation                      → Engine.jsx  <AblationPanel/>
 *   guardrail bus + event stream  → Engine.jsx  <GuardrailPanel/>
 *   throughput curve (inline SVG) → Engine.jsx  <Curve/>
 *   containment tiers + policy    → Engine.jsx  <ContainmentPanel/>
 *   the seam() honesty badge      → common.jsx  <Seam/>
 *
 * The curve's hardcoded hex (#E0A44C etc.) is gone — it reads CSS custom
 * properties now, so the chart re-themes with everything else.
 *
 * See git history for the original implementation. */
