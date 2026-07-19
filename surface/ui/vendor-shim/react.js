/* React is loaded as a UMD global by the shell (static/vendor/react.production.min.js)
 * rather than bundled, so the bundle stays small and the library is a separate,
 * cacheable, auditable file. The build aliases the bare `react` specifier onto
 * this shim; the design-system components keep their ordinary `import React
 * from 'react'` and never learn about the global. */

const React = globalThis.React;

if (!React) {
  throw new Error(
    'React global missing — static/vendor/react.production.min.js must load before airtight-kit.js'
  );
}

export default React;
export const {
  Fragment,
  createElement,
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
} = React;
