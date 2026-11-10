// 온보딩 초안 보관: 바뀐 항목만 골라내고, 웹 sessionStorage / 앱 SecureStore 에 저장·복원하며, 손상된 값은 버린다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const same = (a, b) => assert.equal(JSON.stringify(a), JSON.stringify(b));   // vm 객체는 프로토타입이 달라 deepEqual 불가

function load(platform, session, secureMap = new Map()) {
  const file = path.resolve(__dirname, '../src/state/draft-store.ts');
  const mod = { exports: {} };
  const secure = { getItemAsync: async (k) => secureMap.get(k) ?? null, setItemAsync: async (k, v) => { secureMap.set(k, v); }, deleteItemAsync: async (k) => { secureMap.delete(k); } };
  const ctx = { module: mod, exports: mod.exports, JSON, Error, Promise, Object, sessionStorage: session,
    require(name) {
      if (name === 'expo-secure-store') return secure;
      if (name === 'react-native') return { Platform: { OS: platform } };
      throw new Error(name);
    } };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, ctx, { filename: file });
  return mod.exports;
}
const empty = { gender: 'undisclosed', birth_year: null, height_cm: null, pc_season: null, pc_subtone: null, body_type: null, mbti: null };
const saved = { gender: 'female', birth_year: 1993, height_cm: 162, pc_season: 'spring', pc_subtone: 'warm', body_type: 'straight', mbti: 'ENFP' };

(async () => {
  const store = new Map();
  const session = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) };
  const web = load('web', session);
  // 바뀐 항목만: 손대지 않은 저장값은 patch 에 들어가지 않는다 (F022 의 핵심)
  same(web.touchedFields({ ...saved, mbti: 'INTJ' }, saved), { mbti: 'INTJ' });
  same(web.touchedFields(saved, saved), {});
  same(web.touchedFields({ ...empty, gender: 'male' }, empty), { gender: 'male' });
  same(web.touchedFields({ ...saved, height_cm: undefined }, saved), { height_cm: null });
  assert.equal(web.sameProfile(empty, { ...empty }), true);
  assert.equal(web.sameProfile(empty, saved), false);
  // 웹: sessionStorage 저장·복원·삭제
  assert.equal(await web.readDraft(), null);
  await web.writeDraft({ profile: { ...empty, gender: 'female' }, original: saved });
  assert.deepEqual(JSON.parse(store.get('photospot.onboarding-draft')).original, saved);
  same(await web.readDraft(), { profile: { ...empty, gender: 'female' }, original: saved });
  await web.writeDraft(null);
  assert.equal(store.has('photospot.onboarding-draft'), false);
  // 손상된 값·저장소 오류는 조용히 null
  store.set('photospot.onboarding-draft', '{not json');
  assert.equal(await web.readDraft(), null);
  store.set('photospot.onboarding-draft', JSON.stringify({ profile: { nope: 1 } }));
  assert.equal(await web.readDraft(), null);
  store.set('photospot.onboarding-draft', JSON.stringify({ profile: empty, original: 'x' }));
  same(await web.readDraft(), { profile: empty, original: null });
  const blocked = load('web', { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } });
  await blocked.writeDraft({ profile: empty, original: null });
  assert.equal(await blocked.readDraft(), null);
  // 앱: SecureStore
  const secureMap = new Map();
  const app = load('ios', undefined, secureMap);
  await app.writeDraft({ profile: saved, original: null });
  assert.equal(secureMap.has('photospot.onboarding-draft'), true);
  same(await app.readDraft(), { profile: saved, original: null });
  await app.writeDraft(null);
  assert.equal(secureMap.size, 0);
  console.log('Draft store: touched fields only, web/native persistence, corrupt values ignored.');
})().catch((e) => { console.error(e); process.exitCode = 1; });
