// 로그인 뒤 돌아갈 딥링크: 알려진 SPA 경로만 기억하고, 한 번 꺼내면 지우며, 앱 스킴·웹 주소를 라우터 경로로 바꾼다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');

function load(session) {
  const file = path.resolve(__dirname, '../src/state/auth-session.ts');
  const mod = { exports: {} };
  const ctx = { module: mod, exports: mod.exports, Set, Error, Promise, Object, RegExp, require() { throw new Error('no imports expected'); } };
  if (session) ctx.sessionStorage = session;
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, ctx, { filename: file });
  return mod.exports;
}

(async () => {
  const store = new Map();
  const session = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) };
  const m = load(session);
  // 기억할 만한 경로
  for (const href of ['/place/abc-123', '/place/x?date=2026-11-09', '/diagnosis/personal-color', '/diagnosis/body-type', '/feedback/42', '/saju', '/saved', '/settings', '/result']) {
    assert.equal(m.isDeepLinkRoute(href), true, href);
  }
  // 기억하지 않는 경로: 대문·로그인·온보딩·외부·이상한 값
  for (const href of ['/', '/login', '/onboarding/basic', '/oauth/naver?code=1', '/admin', 'https://evil.test/place/x', '//evil.test', '/place/', '/place/a/b', '/diagnosis/other', '/place/' + 'a'.repeat(2000)]) {
    assert.equal(m.isDeepLinkRoute(href), false, href);
    assert.equal(m.rememberIntendedRoute(href), false, href);
  }
  assert.equal(m.peekIntendedRoute(), null);
  // 기억 → 엿보기(유지) → 꺼내기(삭제). sessionStorage 에도 남는다 (OAuth 왕복·새로고침)
  assert.equal(m.rememberIntendedRoute('/place/abc?date=2026-11-09'), true);
  assert.equal(store.get('photospot.intended-route'), '/place/abc?date=2026-11-09');
  assert.equal(m.peekIntendedRoute(), '/place/abc?date=2026-11-09');
  assert.equal(m.peekIntendedRoute(), '/place/abc?date=2026-11-09');
  assert.equal(m.takeIntendedRoute(), '/place/abc?date=2026-11-09');
  assert.equal(m.takeIntendedRoute(), null);
  assert.equal(store.has('photospot.intended-route'), false);
  // 새로고침(메모리 비움) 뒤에도 sessionStorage 값은 살아 있다; 저장소의 손상된 값은 무시한다
  store.set('photospot.intended-route', '/diagnosis/personal-color');
  assert.equal(load(session).takeIntendedRoute(), '/diagnosis/personal-color');
  store.set('photospot.intended-route', 'https://evil.test/');
  assert.equal(load(session).peekIntendedRoute(), null);
  // sessionStorage 가 없거나 throw 해도 메모리로 동작한다 (네이티브·사생활 보호 모드)
  const mem = load(undefined);
  assert.equal(mem.rememberIntendedRoute('/saved'), true);
  assert.equal(mem.takeIntendedRoute(), '/saved');
  const broken = load({ getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } });
  assert.equal(broken.rememberIntendedRoute('/saved'), true);
  assert.equal(broken.peekIntendedRoute(), '/saved');
  m.clearIntendedRoute();

  // URL → 라우터 경로
  assert.equal(m.hrefFromUrl('https://photospot.litaandd.com/place/abc?date=2026-11-09#top'), '/place/abc?date=2026-11-09');
  assert.equal(m.hrefFromUrl('https://photospot.litaandd.com/'), '/');
  assert.equal(m.hrefFromUrl('https://photospot.litaandd.com'), '/');
  assert.equal(m.hrefFromUrl('photospot://place/abc'), '/place/abc');
  assert.equal(m.hrefFromUrl('photospot://diagnosis/body-type?utm_source=qr'), '/diagnosis/body-type?utm_source=qr');
  assert.equal(m.hrefFromUrl('exp://192.168.0.2:8081/--/place/abc'), '/place/abc');
  assert.equal(m.hrefFromUrl('/saved'), '/saved');
  assert.equal(m.hrefFromUrl('saved'), null);
  assert.equal(m.hrefFromUrl(null), null);
  assert.equal(m.hrefFromUrl(''), null);

  // 토큰 저장소 구독: 저장·삭제가 로그인 상태를 알린다
  const events = [];
  const tokens = m.observableTokens({ async get() { return null; }, async set() {}, async clear() {} });
  const unsubscribe = m.onSessionChange((v) => events.push(v));
  await tokens.set({ access: 'a', refresh: 'b' }); await tokens.clear(); unsubscribe(); await tokens.set({ access: 'a', refresh: 'b' });
  assert.deepEqual(events, [true, false]);
  console.log('Auth session: deep-link allowlist, remember/peek/take with sessionStorage fallback, url → href, token change events.');
})().catch((e) => { console.error(e); process.exitCode = 1; });
