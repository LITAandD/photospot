// 웹 폰트(F004): Google Fonts CSS의 @font-face를 theme.ts 가족명으로 복제하고, CSS는 한 번만 요청하며, 실패해도 첫 화면을 막지 않는다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const file = path.resolve(__dirname, '../src/fonts.web.ts');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
  module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true } }).outputText,
  { module: mod, exports: mod.exports, console, Promise, require: name => { assert.equal(name, 'react'); return { useEffect() {} }; } }, { filename: file });
const { GOOGLE_FONTS_CSS, FAMILY_ALIASES, aliasRules, loadWebFonts, useAppFonts } = mod.exports;

assert.ok(GOOGLE_FONTS_CSS.startsWith('https://fonts.googleapis.com/css2?'));
assert.match(GOOGLE_FONTS_CSS, /display=swap/);
assert.match(GOOGLE_FONTS_CSS, /family=Gowun\+Batang:wght@700/);
assert.match(GOOGLE_FONTS_CSS, /family=IBM\+Plex\+Sans\+KR:wght@400;500;600/);
// theme.ts가 쓰는 네 가족명이 모두 별칭에 있다.
const theme = fs.readFileSync(path.resolve(__dirname, '../src/theme.ts'), 'utf8');
for (const name of ['GowunBatang_700Bold', 'IBMPlexSansKR_400Regular', 'IBMPlexSansKR_500Medium', 'IBMPlexSansKR_600SemiBold']) {
  assert.ok(theme.includes(`"${name}"`), name + ' in theme.ts');
  assert.ok(Object.values(FAMILY_ALIASES).some(weights => Object.values(weights).includes(name)), name + ' aliased');
}
assert.ok(!fs.readFileSync(file, 'utf8').includes('@expo-google-fonts'), '웹 번들에 TTF를 싣지 않는다');

const face = (family, weight, range) => ({ cssText: `@font-face { font-family: ${family}; font-style: normal; font-weight: ${weight}; font-display: swap; src: url("https://fonts.gstatic.com/s/x/${weight}.woff2") format("woff2"); unicode-range: ${range}; }` });
const rules = [face('"Gowun Batang"', 700, 'U+AC00-D7A3'), face("'IBM Plex Sans KR'", 400, 'U+0000-00FF'), face('"IBM Plex Sans KR"', 600, 'U+1100-11FF'),
  face('"IBM Plex Sans KR"', 300, 'U+0000-00FF'), face('"Other"', 400, 'U+0000-00FF'), { cssText: '.x { color: red; }' }];
const css = aliasRules(rules);
const faces = css.split('\n');
assert.equal(faces.length, 3, '알 수 없는 가족·굵기와 일반 규칙은 빼고 조각마다 한 규칙');
assert.match(faces[0], /^@font-face \{ font-family: GowunBatang_700Bold; .*unicode-range: U\+AC00-D7A3; \}$/);
assert.match(faces[1], /font-family: IBMPlexSansKR_400Regular;/);
assert.match(faces[2], /font-family: IBMPlexSansKR_600SemiBold;/);
for (const line of faces) { assert.match(line, /font-display: swap/); assert.match(line, /fonts\.gstatic\.com/); assert.doesNotMatch(line, /Gowun Batang|Plex Sans/); }

function fakeDocument({ readable = true, fail = false } = {}) {
  const head = { children: [], append(...nodes) { this.children.push(...nodes); for (const node of nodes) if (node.rel === 'stylesheet') setTimeout(() => fail ? node.onerror() : node.onload()); }, appendChild(node) { this.children.push(node); } };
  const byId = {};
  return { head, byId, createElement(tag) {
    const node = { tag, set id(value) { byId[value] = this; this._id = value; }, get id() { return this._id; } };
    if (tag === 'link') Object.defineProperty(node, 'sheet', { get() { if (!readable) throw new Error('SecurityError'); return { cssRules: rules }; } });
    return node;
  }, getElementById: id => byId[id] ?? null };
}
(async () => {
  let doc = fakeDocument();
  const first = loadWebFonts(doc);
  assert.equal(loadWebFonts(doc), first, 'CSS는 한 번만 요청한다');
  assert.equal(await first, true);
  const link = doc.head.children.find(n => n.rel === 'stylesheet');
  assert.equal(link.href, GOOGLE_FONTS_CSS);
  assert.equal(link.crossOrigin, 'anonymous', 'cssRules를 읽으려면 CORS 링크여야 한다');
  assert.ok(doc.head.children.some(n => n.rel === 'preconnect' && n.href === 'https://fonts.gstatic.com'));
  assert.equal(doc.byId['app-font-aliases'].textContent, css);
  assert.equal(useAppFonts(), true, '폰트를 기다리지 않고 첫 화면을 그린다');
  console.log('fonts.web ok');
})().catch(error => { console.error(error); process.exit(1); });
