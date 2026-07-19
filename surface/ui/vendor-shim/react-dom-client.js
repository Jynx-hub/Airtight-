/* Companion to ./react.js — maps `react-dom/client` onto the UMD global loaded
 * by the shell. React 18's UMD build exposes createRoot directly. */

const ReactDOM = globalThis.ReactDOM;

if (!ReactDOM || !ReactDOM.createRoot) {
  throw new Error(
    'ReactDOM global missing — static/vendor/react-dom.production.min.js must load before airtight-kit.js'
  );
}

export const createRoot = ReactDOM.createRoot;
export default ReactDOM;
