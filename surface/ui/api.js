/* The JSON contract, in one place.
 *
 * Every function here maps 1:1 onto a route in surface/app.py — see the table
 * in surface/README.md. Nothing in the UI fetches a URL directly, so a route
 * rename has exactly one call site to fix. */

const json = async (url, init) => {
  const res = await fetch(url, init);
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
};

const post = (url, body) =>
  json(url, {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  });

export const health = () => json('/api/health');
export const sample = () => json('/api/sample');

/* ---- drafting ---- */

export const startDraft = (disclosure) => post('/api/draft/start', disclosure);
export const draftStatus = (jobId) => json(`/api/draft/${jobId}`);

export const patchClaims = (jobId, claims) =>
  json(`/api/draft/${jobId}`, {
    method: 'PATCH',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ claims }),
  });

/* ---- retrieval ---- */

export const retrieve = (disclosure) => post('/api/memory/retrieve', disclosure);
export const retrieveById = (id) => json(`/api/memory/retrieve/${id}`);

/* ---- engine reads (all tolerant; a missing artifact comes back as a seam) ---- */

export const memoryStats = () => json('/api/memory/stats');
export const disclosures = () => json('/api/disclosures');
export const ablation = () => json('/api/ablation');
export const security = () => json('/api/security');
export const throughput = () => json('/api/throughput');
export const containment = () => json('/api/containment');

export const memoryRecords = ({ statute = '', cpc = '', q = '', limit = 60 } = {}) =>
  json(`/api/memory/records?${new URLSearchParams({ statute, cpc, q, limit })}`);
