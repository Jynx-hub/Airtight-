import React from 'react';
import ReactDOM from 'react-dom/client';
import { App } from './App.jsx';

/* Entry point. React and ReactDOM come from the vendored UMD globals loaded by
 * the shell (static/vendor/), so esbuild is told to treat them as external and
 * map the bare specifiers onto window.React / window.ReactDOM. */

const root = document.getElementById('root');

// The shell names the frame it was served as, so `/admin` renders the engine on
// first paint rather than flashing intake and correcting itself.
ReactDOM.createRoot(root).render(
  <App initialView={root.dataset.view || undefined} />
);
