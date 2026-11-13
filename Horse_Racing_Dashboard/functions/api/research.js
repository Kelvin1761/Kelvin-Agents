// Projection cache only. Never read or write the betting ledger or evidence store.
const PREFIX = 'STAGE5_RESEARCH_V1:';
const MAX_BYTES = 256 * 1024;
// Permit at most five minutes of publisher clock skew, never an unbounded future pointer.
const MAX_FUTURE_SKEW_MS = 5 * 60 * 1000;
const DOMAINS = ['au', 'hkjc', 'tennis', 'nba'];
const SHA = /^[a-f0-9]{64}$/;
const HEADERS = { 'Content-Type': 'application/json; charset=utf-8',
  'Cache-Control': 'private, no-store', 'X-Content-Type-Options': 'nosniff',
  'Vary': 'Authorization', 'Referrer-Policy': 'no-referrer' };
const reply = (body, status = 200) => new Response(JSON.stringify(body), { status, headers: HEADERS });
function access({ request, env }) {
  if (typeof env.WC_SYNC_TOKEN !== 'string' || !env.WC_SYNC_TOKEN.trim()) return reply({ error: 'private_access_not_configured' }, 503);
  const origin = request.headers.get('Origin');
  const site = request.headers.get('Sec-Fetch-Site');
  if ((origin && origin !== new URL(request.url).origin) ||
      (site && !['same-origin', 'none'].includes(site)) ||
      request.headers.get('Authorization') !== `Bearer ${env.WC_SYNC_TOKEN}`) return reply({ error: 'unauthorized' }, 401);
  if (!env.WC_STATE?.get || !env.WC_STATE?.put) return reply({ error: 'projection_storage_unavailable' }, 503);
  return null;
}
function finiteTree(value, depth = 0) {
  if (depth > 40) throw new Error('depth');
  if (typeof value === 'number' && !Number.isFinite(value)) throw new Error('number');
  if (value && typeof value === 'object') for (const item of Object.values(value)) finiteTree(item, depth + 1);
}
function validate(value) {
  const keys = ['schema_version', 'domain', 'as_of', 'projection', 'model_promotion_allowed', 'current_state_verified'];
  if (!value || Object.keys(value).sort().join('|') !== keys.sort().join('|') ||
      value.schema_version !== 'wong-choi-private-research-feed/v1' || !DOMAINS.includes(value.domain) ||
      typeof value.as_of !== 'string' || !/T.*(?:Z|[+-]\d\d:\d\d)$/.test(value.as_of) ||
      !Number.isFinite(Date.parse(value.as_of)) || Date.parse(value.as_of) > Date.now() + MAX_FUTURE_SKEW_MS || value.current_state_verified !== false ||
      value.model_promotion_allowed !== false) throw new Error('publication');
  const p = value.projection;
  if (!p || p.schema_version !== 'wong-choi-research-presentation/v1' || p.domain !== value.domain ||
      p.as_of !== value.as_of || !SHA.test(p.receipt_hash) || !SHA.test(p.content_hash) ||
      p.evidence_scope !== 'receipt_snapshot_hash_and_lineage_not_source_reaudit' ||
      p.verified_monitoring_samples !== null || typeof p.freeze_research_required !== 'boolean' ||
      !Array.isArray(p.freeze_reasons) || !Array.isArray(p.findings) ||
      ['safety_recomputed', 'model_promotion_allowed', 'rerun_scoring_allowed', 'reevaluate_promotion_allowed']
        .some(key => p[key] !== false) || !Array.isArray(p.experiments) || !Array.isArray(p.queue) ||
      !p.counts || Array.isArray(p.counts) || typeof p.counts !== 'object') throw new Error('projection');
  const c = p.counts;
  if (['experiments', 'runs', 'reports_not_supplied', 'reports_hash_linked'].some(key =>
      !Number.isSafeInteger(c[key]) || c[key] < 0) || c.experiments !== p.experiments.length ||
      !c.decisions || Array.isArray(c.decisions) || typeof c.decisions !== 'object' ||
      !c.run_states || Array.isArray(c.run_states) || typeof c.run_states !== 'object' ||
      [...Object.values(c.decisions), ...Object.values(c.run_states)].some(n => !Number.isSafeInteger(n) || n < 0)) throw new Error('counts');
  finiteTree(value);
  return value;
}
async function digest(raw) {
  const hash = await crypto.subtle.digest('SHA-256', new TextEncoder().encode(raw));
  return [...new Uint8Array(hash)].map(n => n.toString(16).padStart(2, '0')).join('');
}
function bounded(raw) {
  if (typeof raw !== 'string' || new TextEncoder().encode(raw).length > MAX_BYTES) throw new Error('size');
  return validate(JSON.parse(raw));
}
async function readSnapshot(kv, domain, hash) {
  if (!SHA.test(hash)) throw new Error('hash');
  const raw = await kv.get(`${PREFIX}blob:${hash}`);
  const publication = bounded(raw);
  if (await digest(raw) !== hash || publication.domain !== domain) throw new Error('stored_identity');
  return { sha256: hash, publication };
}
async function current(kv, domain) {
  const raw = await kv.get(`${PREFIX}latest:${domain}`);
  if (raw === null) return null;
  if (typeof raw !== 'string' || raw.length > 512) throw new Error('pointer');
  const pointer = JSON.parse(raw);
  const stored = await readSnapshot(kv, domain, pointer.sha256);
  if (pointer.as_of !== stored.publication.as_of) throw new Error('pointer_identity');
  return stored;
}
async function readBody(request) {
  const reader = request.body?.getReader();
  if (!reader) throw new Error('empty');
  const chunks = []; let size = 0;
  try {
    while (true) {
      const { done, value } = await reader.read();
      if (done) break;
      size += value.byteLength;
      if (size > MAX_BYTES) { await reader.cancel(); throw new Error('too_large'); }
      chunks.push(value);
    }
  } finally { reader.releaseLock(); }
  const bytes = new Uint8Array(size); let offset = 0;
  for (const chunk of chunks) { bytes.set(chunk, offset); offset += chunk.byteLength; }
  return new TextDecoder('utf-8', { fatal: true }).decode(bytes);
}
export async function onRequestGet(context) {
  const denied = access(context); if (denied) return denied;
  const url = new URL(context.request.url);
  const selected = url.searchParams.get('domain');
  const hash = url.searchParams.get('sha256');
  if ((selected && !DOMAINS.includes(selected)) || (hash && (!selected || !SHA.test(hash)))) return reply({ error: 'invalid_selector' }, 422);
  try {
    const snapshots = [], missing = [];
    for (const domain of selected ? [selected] : DOMAINS) {
      const item = hash ? await readSnapshot(context.env.WC_STATE, domain, hash) : await current(context.env.WC_STATE, domain);
      if (item) snapshots.push(item); else missing.push(domain);
    }
    return reply({ schema_version: 'wong-choi-private-research-list/v1', snapshots, missing,
      current_state_verified: false, model_promotion_allowed: false });
  } catch { return reply({ error: 'projection_unavailable_or_invalid' }, 503); }
}
export async function onRequestPost(context) {
  const denied = access(context); if (denied) return denied;
  if (!/^application\/json(?:;|$)/i.test(context.request.headers.get('Content-Type') || '')) return reply({ error: 'json_required' }, 415);
  let raw, publication;
  try { raw = await readBody(context.request); publication = bounded(raw); }
  catch (error) { return reply({ error: 'invalid_projection' }, error.message === 'too_large' ? 413 : 422); }
  try {
    const kv = context.env.WC_STATE, hash = await digest(raw), domain = publication.domain;
    const previous = await current(kv, domain);
    if (previous && Date.parse(publication.as_of) <= Date.parse(previous.publication.as_of) && previous.sha256 !== hash) return reply({ error: 'stale_or_conflicting_projection' }, 409);
    const key = `${PREFIX}blob:${hash}`, existing = await kv.get(key);
    if (existing !== null && existing !== raw) return reply({ error: 'immutable_projection_conflict' }, 409);
    if (existing === null) await kv.put(key, raw);
    // Best-effort cache pointer, NOT a cross-writer CAS or authoritative history.
    // Every archived projection retains its content-addressed key and as-of date.
    if (previous?.sha256 !== hash) await kv.put(`${PREFIX}latest:${domain}`, JSON.stringify({ sha256: hash, as_of: publication.as_of }));
    return reply({ status: previous?.sha256 === hash ? 'already_stored' : 'stored', domain, sha256: hash, model_promotion_allowed: false });
  } catch { return reply({ error: 'projection_storage_failed' }, 503); }
}
