import assert from 'node:assert/strict';
import test from 'node:test';
import { webcrypto } from 'node:crypto';
import { onRequestGet, onRequestPost } from '../functions/api/research.js';

globalThis.crypto ||= webcrypto;
const token = 'isolated-test-token';
const values = new Map();
const env = () => ({ WC_SYNC_TOKEN: token, WC_STATE: {
  get: async key => values.get(key) ?? null,
  put: async (key, value) => values.set(key, value),
} });
function payload(asOf = '2026-11-13T00:00:00+00:00') {
  return { schema_version: 'wong-choi-private-research-feed/v1', domain: 'au', as_of: asOf,
    projection: { schema_version: 'wong-choi-research-presentation/v1', domain: 'au', as_of: asOf,
      receipt_hash: 'a'.repeat(64), content_hash: 'b'.repeat(64),
      freeze_research_required: true, freeze_reasons: [], findings: [],
      verified_monitoring_samples: null, evidence_scope: 'receipt_snapshot_hash_and_lineage_not_source_reaudit',
      safety_recomputed: false, model_promotion_allowed: false, rerun_scoring_allowed: false,
      reevaluate_promotion_allowed: false, counts: { experiments: 0, runs: 0, decisions: {}, run_states: {},
        reports_not_supplied: 0, reports_hash_linked: 0 }, experiments: [], queue: [] },
    model_promotion_allowed: false, current_state_verified: false };
}
function request(method, body, authorization = token) {
  return new Request('https://dashboard.example/api/research?domain=au', {
    method, headers: { ...(authorization ? { Authorization: `Bearer ${authorization}` } : {}),
      'Content-Type': 'application/json' }, ...(body === undefined ? {} : { body: JSON.stringify(body) }),
  });
}
test('private research never falls back to same-origin authorization', async () => {
  for (const method of ['GET', 'POST']) {
    const handler = method === 'GET' ? onRequestGet : onRequestPost;
    const req = request(method, method === 'POST' ? payload() : undefined, null);
    assert.equal((await handler({ request: req, env: { WC_STATE: env().WC_STATE } })).status, 503);
    assert.equal((await handler({ request: req, env: env() })).status, 401);
  }
  assert.equal(values.size, 0);
});
test('publish then authorized read uses dedicated projection keys and immutable hash', async () => {
  values.clear();
  const post = await onRequestPost({ request: request('POST', payload()), env: env() });
  assert.equal(post.status, 200);
  const ack = await post.json();
  assert.match(ack.sha256, /^[a-f0-9]{64}$/);
  assert.equal(ack.model_promotion_allowed, false);
  const get = await onRequestGet({ request: request('GET'), env: env() });
  assert.match(get.headers.get('Cache-Control'), /no-store/);
  const body = await get.json();
  assert.deepEqual(body.snapshots[0].publication, payload());
  assert.equal(body.current_state_verified, false);
  assert.ok([...values.keys()].every(key => key.startsWith('STAGE5_RESEARCH_V1:')));
  const replay = await onRequestPost({ request: request('POST', payload()), env: env() });
  assert.equal((await replay.json()).status, 'already_stored');
});
test('bad authority, stale replacement and corrupt storage fail closed', async () => {
  values.clear();
  await onRequestPost({ request: request('POST', payload()), env: env() });
  const before = new Map(values);
  const bad = payload(); bad.projection.model_promotion_allowed = true;
  assert.equal((await onRequestPost({ request: request('POST', bad), env: env() })).status, 422);
  assert.equal((await onRequestPost({ request: request('POST', payload('2026-11-12T00:00:00Z')), env: env() })).status, 409);
  assert.deepEqual(values, before);
  const blobKey = [...values.keys()].find(key => !key.endsWith(':latest:au'));
  values.set(blobKey, '{}');
  assert.equal((await onRequestGet({ request: request('GET'), env: env() })).status, 503);
});
test('wrong tokens, cross-origin and unbounded streams cannot read or publish', async () => {
  values.clear();
  assert.equal((await onRequestGet({ request: request('GET', undefined, 'wrong'), env: env() })).status, 401);
  const cross = request('POST', payload()); cross.headers.set('Origin', 'https://attacker.example');
  assert.equal((await onRequestPost({ request: cross, env: env() })).status, 401);
  const large = new Request('https://dashboard.example/api/research', {method: 'POST',
    headers: {'Authorization': `Bearer ${token}`, 'Content-Type': 'application/json'}, body: ' '.repeat(256 * 1024 + 1)});
  assert.equal((await onRequestPost({ request: large, env: env() })).status, 413);
  assert.equal(values.size, 0);
});
test('old content-addressed snapshots remain readable without any ledger binding', async () => {
  values.clear();
  const first = await (await onRequestPost({ request: request('POST', payload()), env: env() })).json();
  assert.equal((await onRequestPost({request: request('POST', payload('2026-11-13T00:01:00Z')), env: env()})).status, 200);
  const req = new Request(`https://dashboard.example/api/research?domain=au&sha256=${first.sha256}`,
    {headers: {Authorization: `Bearer ${token}`}});
  assert.deepEqual((await (await onRequestGet({request: req, env: env()})).json()).snapshots[0].publication, payload());
  assert.equal(values.has('GLOBAL_BETS'), false);
});
test('missing freeze state and future dates are rejected before cache writes', async () => {
  for (const change of [p => {delete p.projection.freeze_research_required;},
    p => {p.projection.freeze_research_required = 'false';},
    p => {p.as_of = p.projection.as_of = new Date(Date.now() + 301000).toISOString();}]) {
    values.clear(); const p = payload(); change(p);
    assert.equal((await onRequestPost({request: request('POST', p), env: env()})).status, 422);
    assert.equal(values.size, 0);
  }
});
