import assert from 'node:assert/strict';
import test from 'node:test';
import { webcrypto } from 'node:crypto';
import { readFileSync } from 'node:fs';
import vm from 'node:vm';
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
function viewHarness(fetcher) {
  class Element {
    constructor(tag) { this.tag = tag; this.children = []; this.style = {}; this.textContent = ''; }
    replaceChildren() { this.children = []; this.textContent = ''; }
    appendChild(node) { this.children.push(node); }
    showModal() { this.open = true; }
    set innerHTML(_) { throw new Error('unsafe HTML rendering'); }
  }
  const content = new Element('div'), dialog = new Element('dialog');
  const document = {createElement: tag => new Element(tag), getElementById: id =>
    id === 'research-feed-content' ? content : dialog};
  const source = readFileSync(new URL('../static_template.html', import.meta.url), 'utf8')
    .split('// BEGIN PRIVATE RESEARCH VIEW')[1].split('// END PRIVATE RESEARCH VIEW')[0];
  // First line is the marker's comment suffix.
  const context = vm.createContext({document, window: {location: {protocol: 'https:'}}, authorizedFetch: fetcher});
  vm.runInContext(source.slice(source.indexOf('\n') + 1), context);
  const text = node => [node.textContent, ...node.children.map(text)].join(' ');
  return {context, content, text};
}
test('actual template renders untrusted hypotheses as text and retains freeze warning', () => {
  const h = viewHarness(); const p = payload();
  p.projection.experiments.push({spec_id: 'test', hypothesis: '<img src=x onerror=alert(1)>'});
  h.context.renderResearchFeed(h.content, {schema_version: 'wong-choi-private-research-list/v1',
    current_state_verified: false, model_promotion_allowed: false, missing: [],
    snapshots: [{sha256: 'c'.repeat(64), publication: p}]});
  assert.match(h.text(h.content), /研究凍結/);
  assert.match(h.text(h.content), /發布端報告/);
  assert.match(h.text(h.content), /<img src=x onerror=alert\(1\)>/);
  delete p.projection.freeze_research_required;
  assert.throws(() => h.context.renderResearchFeed(h.content, {schema_version: 'wong-choi-private-research-list/v1',
    current_state_verified: false, model_promotion_allowed: false, missing: [],
    snapshots: [{sha256: 'c'.repeat(64), publication: p}]}));
  assert.equal(h.content.children.length, 0);
});
test('actual template clears old private content and never echoes failed response bodies', async () => {
  let calls = 0;
  const h = viewHarness(async (url, options) => {
    calls++; assert.equal(url, '/api/research'); assert.equal(options.redirect, 'error');
    return {ok: false, text: async () => 'private server secret'};
  });
  h.content.textContent = 'old private data';
  await h.context.openResearchFeed();
  assert.equal(calls, 1);
  assert.match(h.content.textContent, /未能載入/);
  assert.doesNotMatch(h.content.textContent, /old private data|private server secret/);
});
