// 웹 빌드 후처리(scripts/build-web-preview.cjs)가 넣는 공유·검색 메타: 한 번만 주입되고, og/twitter/canonical/파비콘/manifest 가 모두 있으며 자산 파일이 app/public 에 있다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');

const root = path.resolve(__dirname, '../..');
const source = fs.readFileSync(path.join(root, 'scripts/build-web-preview.cjs'), 'utf8');
/** 빌드 스크립트는 실행 시 npm 빌드를 돌리므로, 메타 블록만 잘라 평가한다 (블록 머리글과 `const entry =` 사이) */
function metaInjector(env = {}) {
  const start = source.indexOf('// --- 공유 미리보기·검색·설치 메타 (ux-flows)');
  const end = source.indexOf('const entry = withMeta(');
  assert.ok(start > 0 && end > start, '빌드 스크립트의 메타 블록을 찾지 못했어요');
  const ctx = { process: { env }, module: {}, Error };
  vm.runInNewContext(source.slice(start, end) + '\nmodule.exports = { withMeta, META, PUBLIC_WEB_URL };', ctx);
  return ctx.module.exports;
}
const sample = '<!DOCTYPE html><html lang="ko"><head><meta charset="utf-8"><title>포토스팟</title><style>x</style></head><body></body></html>';
const { withMeta, PUBLIC_WEB_URL } = metaInjector();
const html = withMeta(sample);
assert.equal(PUBLIC_WEB_URL, 'https://photospot.litaandd.com');
for (const tag of [
  '<meta name="description" content="',
  '<meta property="og:title" content="포토스팟',
  '<meta property="og:description" content="',
  '<meta property="og:image" content="https://photospot.litaandd.com/og.png">',
  '<meta property="og:url" content="https://photospot.litaandd.com/">',
  '<meta property="og:image:width" content="1200">',
  '<meta name="twitter:card" content="summary_large_image">',
  '<link rel="canonical" href="https://photospot.litaandd.com/">',
  '<link rel="icon" href="/favicon.ico"',
  '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
  '<link rel="manifest" href="/manifest.json">',
  '<meta name="theme-color" content="#F6F3EE">',
]) assert.ok(html.includes(tag), tag);
assert.equal(html.indexOf('<title>포토스팟</title>'), sample.indexOf('<title>포토스팟</title>'), '제목 앞은 그대로');
assert.equal(withMeta(html), html, '두 번 실행해도 한 번만 주입');
assert.throws(() => withMeta('<html><head><title>다른 제목</title></head></html>'), /찾지 못했어요/);
// 배포 환경 변수로 도메인을 바꾸면 og:url·canonical·이미지 주소가 따라간다
const other = metaInjector({ PUBLIC_BASE_URL: 'https://preview.example.test/' }).withMeta(sample);
assert.ok(other.includes('<link rel="canonical" href="https://preview.example.test/">'));
assert.ok(other.includes('content="https://preview.example.test/og.png"'));
// 메타가 가리키는 정적 자산이 app/public 에 있고 크기가 맞다
for (const file of ['og.png', 'favicon.ico', 'apple-touch-icon.png', 'manifest.json', 'icon-192.png', 'icon-512.png']) {
  assert.ok(fs.existsSync(path.join(root, 'app/public', file)), `app/public/${file}`);
}
const png = fs.readFileSync(path.join(root, 'app/public/og.png'));
assert.deepEqual([png.readUInt32BE(16), png.readUInt32BE(20)], [1200, 630], 'og.png 는 1200x630');
const manifest = JSON.parse(fs.readFileSync(path.join(root, 'app/public/manifest.json'), 'utf8'));
assert.equal(manifest.name, '포토스팟');
assert.equal(manifest.display, 'standalone');
assert.ok(manifest.icons.some((i) => i.sizes === '512x512'));
// 빌드 스크립트는 복사 뒤 자산이 빠지면 멈춘다
assert.ok(source.includes("'og.png', 'favicon.ico', 'apple-touch-icon.png', 'manifest.json'"));
console.log('Web meta: description/og/twitter/canonical/icons/manifest injected once; public assets present (og.png 1200x630).');
