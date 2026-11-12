// 익명 계측: payload 는 {event, route(경로만), session_id(무작위·저장), utm, props} 뿐이고, DEMO 웹은 /preview/events, 계정 API 빌드는 로그인 전에도 /v1/events(로그인 시 Bearer 추가), 실패해도 throw 하지 않는다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load({ platform = 'web', env = {}, demo = false, tokens = null, storage = new Map(), session = new Map(), fetchImpl, clock = () => Date.now(), hostname = 'demo.test', search = '', referrer = '' } = {}) {
  const file = path.resolve(__dirname, '../src/analytics.ts');
  const mod = { exports: {} };
  const kv = (m) => ({ getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) });
  const secure = { getItemAsync: async (k) => storage.get(k) ?? null, setItemAsync: async (k, v) => { storage.set(k, v); }, deleteItemAsync: async (k) => { storage.delete(k); } };
  let sequence = 0;
  const ctx = { module: mod, exports: mod.exports, URL, URLSearchParams, Date: { now: clock }, document: { referrer }, JSON, Error, Promise, Object, Array, Math, String, Number,
    process: { env }, localStorage: kv(storage), sessionStorage: kv(session), fetch: fetchImpl,
    window: platform === 'web' ? { location: { origin: 'https://demo.test', hostname, search } } : undefined,
    require(name) {
      if (name === 'expo-crypto') return { randomUUID: () => '12345678-1234-1234-1234-' + String(++sequence).padStart(12, '0') };
      if (name === 'expo-secure-store') return secure;
      if (name === 'react-native') return { Platform: { OS: platform } };
      if (name === '@/api') return { DEMO: demo, tokenStore: { get: async () => tokens } };
      throw new Error(name);
    } };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, ctx, { filename: file });
  return mod.exports;
}

(async () => {
  const sent = [], storage = new Map([['photospot.analytics.sid', 'legacy_browser_identifier']]), session = new Map();
  let now = 10000000;
  const fetchImpl = async (url, init) => { sent.push({ url, payload: JSON.parse(init.body) }); return { ok: true }; };
  const demo = load({ demo: true, storage, session, fetchImpl, clock: () => now, referrer: 'https://www.litaandd.com/' });
  assert.equal(await demo.track('landing_view'), false, 'existing users are not silently opted in');
  assert.equal(sent.length, 0);
  await demo.setAnalyticsChoice(true);
  assert.equal(storage.has('photospot.analytics.sid'), false, 'legacy browser ID removed, never linked');
  demo.captureUtm('https://demo.test/');
  await demo.track('landing_view');
  const first = sent.at(-1).payload;
  assert.equal(first.utm.utm_source, 'wix');
  assert.equal(first.props.schema_version, 2);
  assert.equal(first.props.traffic, 'production');
  now += 1000;
  await demo.track('place_view', { place_id: 'abc' }, '/place/abc?birth=secret');
  assert.equal(sent.at(-1).payload.session_id, first.session_id);
  assert.equal(sent.at(-1).payload.route, '/place/abc');
  // Reload in same tab keeps the visit. 30 minutes of inactivity starts a different visit.
  const reload = load({ demo: true, storage, session, fetchImpl, clock: () => now });
  assert.equal(await reload.sessionId(), first.session_id);
  now += 30 * 60 * 1000;
  await demo.track('place_view');
  assert.notEqual(sent.at(-1).payload.session_id, first.session_id);
  const count = sent.length;
  await demo.setAnalyticsChoice(false);
  assert.equal(await demo.track('save'), false);
  assert.equal(sent.length, count);
  assert.equal(session.has('photospot.analytics.visit.v2'), false);
  assert.equal(await load({ demo: true, storage, fetchImpl }).analyticsAllowed(), false);
  assert.equal(load({ env: { EXPO_PUBLIC_ANALYTICS: '0' }, demo: true }).analyticsEnabled(), false);
  for (const platform of ['web', 'ios', 'android']) {
    const a = load({ platform, demo: platform === 'web', env: { EXPO_PUBLIC_API_BASE_URL: 'https://api.test' }, fetchImpl, hostname: 'localhost' });
    await a.setAnalyticsChoice(true);
    a.captureUtm('https://demo.test/?utm_source=wix&utm_campaign=launch&utm_term=person%40email.com');
    await a.reportClientError(new RangeError('private input'));
    assert.equal(sent.at(-1).payload.props.message, undefined);
    assert.equal(sent.at(-1).payload.utm.utm_term, undefined);
    assert.equal(sent.at(-1).url, 'https://api.test/' + (platform === 'web' ? 'preview' : 'v1') + '/events');
    if (platform === 'web') assert.equal(sent.at(-1).payload.props.traffic, 'test');
    await a.measuredRecommendations(async () => ({ items: [] }), 'home');
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sent.at(-1).payload.event, 'empty_result');
    assert.equal(sent.at(-1).payload.props.request_id, sent.at(-2).payload.props.request_id);
    await assert.rejects(a.measuredRecommendations(async () => { throw new Error('private'); }, 'home'));
    await new Promise(resolve => setImmediate(resolve));
    assert.equal(sent.at(-1).payload.event, 'recommendation_error');
  }
  for (const fetchImpl of [async () => ({ ok: false }), async () => { throw new Error('offline'); }]) {
    const a = load({ demo: true, fetchImpl }); await a.setAnalyticsChoice(true);
    assert.equal(await a.track('save'), false);
  }
  console.log('Analytics: explicit choice, legacy ID retirement, visits/reload/expiry, Wix, test traffic, request correlation, failure and PII omission pass.');
})().catch(e => { console.error(e); process.exitCode = 1; });
