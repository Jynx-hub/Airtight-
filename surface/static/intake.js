/* Retired — the intake frame is now surface/ui/Intake.jsx, compiled into
 * static/airtight-kit.js by surface/build.sh.
 *
 * This file is deliberately kept rather than deleted: `test_static_assets_are_mounted`
 * in tests/test_surface.py asserts /static/intake.js returns 200, and that test
 * is what guards the StaticFiles mount the whole surface depends on. Nothing
 * loads this script — both shells load airtight-kit.js instead.
 *
 * Everything it used to do lives on, endpoint for endpoint:
 *   sample prefill on load        → Intake.jsx  loadSample()
 *   debounced retrieval preview   → Intake.jsx  previewContext()   (350ms)
 *   job start + 400ms poll        → Intake.jsx  draft() / poll()
 *   claim editing + PATCH         → Intake.jsx  <Claims/>
 *   `/#autodraft` demo rehearsal  → Intake.jsx  boot effect
 *
 * See git history for the original implementation. */
