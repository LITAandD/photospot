// 익명 계측: payload 는 {event, route(경로만), session_id(무작위·저장), utm, props} 뿐이고, DEMO 웹은 /preview/events, 계정 API 빌드는 로그인 전에도 /v1/events(로그인 시 Bearer 추가), 실패해도 throw 하지 않는다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load({ platform = 'web', env = {}, demo = false, tokens = null, storage = new Map(), session = new Map(), fetchImpl } = {}) {
  const file = path.resolve(__dirname, '../src/analytics.ts');
  const mod = { exports: {} };
  const kv = (m) => ({ getItem: (k) => m.get(k) ?? null, setItem: (k, v) => m.set(k, v), removeItem: (k) => m.delete(k) });
  const secure = { getItemAsync: async (k) => storage.get(k) ?? null, setItemAsync: async (k, v) => { storage.set(k, v); }, deleteItemAsync: async (k) => { storage.delete(k); } };
  const ctx = { module: mod, exports: mod.exports, URLSearchParams, JSON, Error, Promise, Object, Array, Math, String, Number,
    process: { env }, localStorage: kv(storage), sessionStorage: kv(session), fetch: fetchImpl,
    window: platform === 'web' ? { location: { origin: 'https://demo.test' } } : undefined,
    require(name) {
      if (name === 'expo-crypto') return { randomUUID: () => '12345678-1234-1234-1234-123456789abc' };
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
  // API 주소도 DEMO 도 아니면 아무것도 보내지 않는다 (개발 빌드)
  const off = load();
  assert.equal(off.analyticsEnabled(), false);
  assert.equal(await off.track('landing_view'), false);
  // 끄기 스위치
  assert.equal(load({ env: { EXPO_PUBLIC_API_BASE_URL: 'https://api.test', EXPO_PUBLIC_ANALYTICS: '0' } }).analyticsEnabled(), false);

  // DEMO 웹: 같은 origin 의 /preview/events, 세션 ID 는 localStorage 에 남는다
  const sent = [];
  const storage = new Map();
  const demo = load({ demo: true, storage, fetchImpl: async (url, init) => { sent.push({ url, init }); return { ok: true }; } });
  demo.captureUtm('https://demo.test/?utm_source=share&utm_medium=result_card&utm_evil=x&utm_campaign=' + 'a'.repeat(300));
  demo.setAnalyticsRoute('/place/abc?date=2026-11-09#x');
  assert.equal(await demo.track('place_view', { place_id: 'abc', has_photo: true, 'bad key': 1, long: 'z'.repeat(500), nothing: undefined }), true);
  assert.equal(sent[0].url, 'https://demo.test/preview/events');
  assert.equal(sent[0].init.method, 'POST');
  assert.equal(sent[0].init.keepalive, true);
  assert.equal(sent[0].init.headers.Authorization, undefined);
  const body = JSON.parse(sent[0].init.body);
  assert.deepEqual(Object.keys(body).sort(), ['event', 'props', 'route', 'session_id', 'utm']);
  assert.equal(body.event, 'place_view');
  assert.equal(body.route, '/place/abc');                                   // 쿼리·해시 제외
  assert.match(body.session_id, /^[A-Za-z0-9_-]{8,64}$/);
  assert.equal(body.session_id, '12345678123412341234123456789abc');
  assert.equal(storage.get('photospot.analytics.sid'), body.session_id);
  assert.deepEqual(body.utm, { utm_source: 'share', utm_medium: 'result_card', utm_campaign: 'a'.repeat(100) });
  assert.deepEqual(body.props, { place_id: 'abc', has_photo: true, long: 'z'.repeat(200) });
  // 저장된 세션 ID 는 다시 쓴다; 손상된 값은 새로 만든다
  const again = load({ demo: true, storage, fetchImpl: async (u, i) => { sent.push({ url: u, init: i }); return { ok: true }; } });
  await again.track('landing_view');
  assert.equal(JSON.parse(sent[1].init.body).session_id, body.session_id);
  assert.equal(JSON.parse(sent[1].init.body).route, '/');
  storage.set('photospot.analytics.sid', 'bad id!');
  const fixed = load({ demo: true, storage, fetchImpl: async (u, i) => { sent.push({ url: u, init: i }); return { ok: true }; } });
  await fixed.track('landing_view');
  assert.notEqual(storage.get('photospot.analytics.sid'), 'bad id!');

  // 로그인(운영 API): /v1/events + Bearer
  const auth = [];
  const signed = load({ env: { EXPO_PUBLIC_API_BASE_URL: 'https://api.test/' }, tokens: { access: 'tok', refresh: 'r' }, fetchImpl: async (u, i) => { auth.push({ u, i }); return { ok: true }; } });
  await signed.track('save', { saved: true });
  assert.equal(auth[0].u, 'https://api.test/v1/events');
  assert.equal(auth[0].i.headers.Authorization, 'Bearer tok');
  // 계정 API 빌드의 로그인 전 이벤트(랜딩·오류 보고)도 /v1/events 로 간다 — 운영 API에는 /preview/events 가 없다
  const anon = [];
  const guest = load({ env: { EXPO_PUBLIC_API_BASE_URL: 'https://api.test/' }, tokens: null, fetchImpl: async (u, i) => { anon.push({ u, i }); return { ok: true }; } });
  await guest.track('landing_view');
  assert.equal(anon[0].u, 'https://api.test/v1/events');
  assert.equal(anon[0].i.headers.Authorization, undefined);
  // 네트워크 실패·전송기 예외는 false 로 끝난다 (UI 를 막지 않음)
  const failing = load({ demo: true, fetchImpl: async () => { throw new TypeError('offline'); } });
  assert.equal(await failing.track('landing_view'), false);
  // 오류 보고: 이름·메시지(200자)·플랫폼만
  const errors = [];
  const reporter = load({ demo: true, fetchImpl: async (u, i) => { errors.push(JSON.parse(i.body)); return { ok: true }; } });
  reporter.setAnalyticsRoute('/home');
  await reporter.reportClientError(new RangeError('x'.repeat(400)));
  assert.equal(errors[0].event, 'client_error');
  assert.deepEqual(errors[0].props, { name: 'RangeError', message: 'x'.repeat(200), platform: 'web' });
  assert.equal(errors[0].route, '/home');
  // 네이티브: SecureStore 에 세션 ID, utm 은 앱 링크에서
  const native = [];
  const app = load({ platform: 'ios', env: { EXPO_PUBLIC_API_BASE_URL: 'https://api.test' }, fetchImpl: async (u, i) => { native.push(JSON.parse(i.body)); return { ok: true }; } });
  app.captureUtm('photospot://place/x?utm_source=qr');
  await app.track('place_view');
  assert.deepEqual(native[0].utm, { utm_source: 'qr' });
  console.log('Analytics: payload shape, route without query, persisted random session id, utm whitelist, preview vs v1 endpoint, never throws.');
})().catch((e) => { console.error(e); process.exitCode = 1; });
