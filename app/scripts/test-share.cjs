// 공유 도우미: 빈 줄 제거, utm 이 붙은 공개 주소, Web Share 없음·실패 → 클립보드 복사, 둘 다 없으면 failed (절대 throw 하지 않는다).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const same = (a, b) => assert.equal(JSON.stringify(a), JSON.stringify(b));   // vm 객체는 프로토타입이 달라 deepEqual 불가

function load(platform, globals) {
  const file = path.resolve(__dirname, '../src/share.ts');
  const mod = { exports: {} };
  const Share = { dismissedAction: 'dismissedAction', sharedAction: 'sharedAction', share: globals.share };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { module: mod, exports: mod.exports, URL, Error, Promise, Object, Array, process: { env: globals.env ?? {} }, globalThis: globals.globalThis ?? {},
    require(name) { if (name === 'react-native') return { Platform: { OS: platform }, Share }; throw new Error(name); } }, { filename: file });
  return mod.exports;
}

(async () => {
  const web = load('web', { globalThis: {} });
  // 메시지: 값 없는 줄은 빠지고 공백은 다듬는다
  assert.equal(web.buildShareMessage(['나의 포토 타입: 여름 쿨', null, '', '  ', false, '어울리는 배경: 바다']), '나의 포토 타입: 여름 쿨\n어울리는 배경: 바다');
  assert.equal(web.shareLine('잘 맞는 빛', []), null);
  assert.equal(web.shareLine('잘 맞는 빛', ['자연광', '', '역광']), '잘 맞는 빛: 자연광, 역광');
  assert.equal(web.shareLine('메모', '  '), null);
  // 주소: 공개 도메인 + 경로 + utm_source (추가 utm 은 앞에)
  assert.equal(web.PUBLIC_WEB_URL, 'https://photospot.litaandd.com');
  assert.equal(web.shareUrl('/', 'share', { utm_medium: 'result_card' }), 'https://photospot.litaandd.com/?utm_medium=result_card&utm_source=share');
  assert.equal(web.shareUrl('/place/abc%20d'), 'https://photospot.litaandd.com/place/abc%20d?utm_source=share');
  assert.equal(web.shareUrl('place/x', 'share', { utm_medium: undefined }), 'https://photospot.litaandd.com/place/x?utm_source=share');
  assert.equal(load('web', { globalThis: {}, env: { EXPO_PUBLIC_WEB_URL: 'https://example.test/' } }).shareUrl('/'), 'https://example.test/?utm_source=share');

  // 웹·navigator.share 없음·클립보드 있음 → copied, 본문은 메시지 + 주소
  const copied = [];
  const clip = load('web', { globalThis: { navigator: { clipboard: { writeText: async (t) => { copied.push(t); } } } } });
  assert.equal(await clip.shareText({ title: 't', lines: ['a', null, 'b'], url: 'https://x.test/?utm_source=share' }), 'copied');
  assert.equal(copied[0], 'a\nb\nhttps://x.test/?utm_source=share');
  assert.equal(clip.SHARE_NOTICE.copied.includes('복사'), true);
  // 웹·둘 다 없음 → failed (throw 없음)
  assert.equal(await web.shareText({ title: 't', lines: ['a'] }), 'failed');
  // 내용이 없으면 failed
  assert.equal(await clip.shareText({ title: 't', lines: [null, ''] }), 'failed');
  // 웹·navigator.share 있음 → Share.share 가 url 을 따로 받는다. 사용자가 닫으면 dismissed
  const calls = [];
  const shared = load('web', { globalThis: { navigator: { share: () => {} } }, share: async (content, options) => { calls.push({ content, options }); return { action: 'sharedAction' }; } });
  assert.equal(await shared.shareText({ title: '제목', lines: ['a'], url: 'https://x.test/' }), 'shared');
  same(calls[0], { content: { title: '제목', message: 'a', url: 'https://x.test/' }, options: { dialogTitle: '제목', subject: '제목' } });
  const aborted = load('web', { globalThis: { navigator: { share: () => {} } }, share: async () => { const e = new Error('cancel'); e.name = 'AbortError'; throw e; } });
  assert.equal(await aborted.shareText({ title: 't', lines: ['a'] }), 'dismissed');
  // 웹·share 가 다른 오류로 실패 → 클립보드로 넘어간다
  const fallback = load('web', { globalThis: { navigator: { share: () => {}, clipboard: { writeText: async () => {} } } }, share: async () => { throw new Error('Share is not supported in this browser'); } });
  assert.equal(await fallback.shareText({ title: 't', lines: ['a'] }), 'copied');
  // 안드로이드: 공유 시트가 url 필드를 무시하므로 본문에 주소를 넣는다
  const android = [];
  const droid = load('android', { share: async (content) => { android.push(content); return { action: 'sharedAction' }; } });
  assert.equal(await droid.shareText({ title: 't', lines: ['a'], url: 'https://x.test/' }), 'shared');
  same(android[0], { title: 't', message: 'a\nhttps://x.test/' });
  const dismissed = load('ios', { share: async () => ({ action: 'dismissedAction' }) });
  assert.equal(await dismissed.shareText({ title: 't', lines: ['a'], url: 'https://x.test/' }), 'dismissed');
  console.log('Share: empty lines dropped, utm url, web-share → clipboard → failed fallbacks, android inline url.');
})().catch((e) => { console.error(e); process.exitCode = 1; });
