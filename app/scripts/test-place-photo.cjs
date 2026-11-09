// 목록·갤러리 썸네일 크기(F034): 위키미디어 320px 썸네일, 웹은 <img> 하나(lazy), 다른 호스트·ND 사진은 그대로.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const root = path.resolve(__dirname, '..');

function transpile(file, jsx) {
  return ts.transpileModule(fs.readFileSync(file, 'utf8'), { compilerOptions: {
    module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, esModuleInterop: true, jsx } }).outputText;
}
function load(file, modules, jsx = ts.JsxEmit.React) {
  const mod = { exports: {} };
  vm.runInNewContext(transpile(file, jsx), { module: mod, exports: mod.exports, console,
    require: name => { if (!(name in modules)) throw new Error('unexpected import ' + name); return modules[name]; } }, { filename: file });
  return mod.exports;
}
const license = load(path.join(root, '../client/src/photo-license.ts'), {});
const react = { createElement: (type, props, ...children) => ({ type, props: { ...(props ?? {}), children } }),
  useState: init => [typeof init === 'function' ? init() : init, () => {}] };
const platform = { OS: 'web' };
const photoModule = load(path.join(root, 'src/components/place-photo.tsx'), {
  react: { __esModule: true, default: react, ...react },
  'react-native': { Image: 'Image', Linking: { openURL: async () => {} }, Platform: platform, Pressable: 'Pressable',
    StyleSheet: { create: s => s, absoluteFill: { position: 'absolute' } }, Text: 'Text', View: 'View' },
  '@/theme': { colors: {}, fonts: {} },
  '@photospot/client': license,
});
const { thumbnailUrl, thumbWidthFor, PlacePhoto, THUMB_WIDTH, SMALL_FRAME_PX } = photoModule;

const utm = '?utm_source=commons.wikimedia.org&utm_campaign=imageinfo&utm_content=thumbnail';
const big = 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Pl%20ace.jpg/960px-Pl%20ace.jpg' + utm;
assert.equal(thumbnailUrl(big, 320), 'https://thumb.wikimedia.org/wikipedia/commons/thumb/a/ab/Pl%20ace.jpg/320px-Pl%20ace.jpg' + utm);
assert.equal(thumbnailUrl(big, 960), big);                                             // 이미 그 크기면 그대로
assert.equal(thumbnailUrl(big, 1280), big);
assert.equal(thumbnailUrl(big, 320, 300), big);                                        // 원본보다 크게 요청하지 않는다
const original = 'https://upload.wikimedia.org/wikipedia/commons/5/5d/Noeul_Park.jpg?utm_content=thumbnail_unscaled';
assert.equal(thumbnailUrl(original, 320, 732), 'https://upload.wikimedia.org/wikipedia/commons/thumb/5/5d/Noeul_Park.jpg/320px-Noeul_Park.jpg?utm_content=thumbnail_unscaled');
assert.equal(thumbnailUrl('https://upload.wikimedia.org/wikipedia/commons/5/5d/Map.svg', 320), 'https://upload.wikimedia.org/wikipedia/commons/5/5d/Map.svg');
for (const untouched of ['https://postfiles.pstatic.net/a/b.jpg?type=w966', 'https://image.istarbucks.co.kr/upload/store/x.jpg',
  'http://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/P.jpg/960px-P.jpg', 'https://upload.wikimedia.org/wikipedia/commons/thumb/a/ab/P.jpg/960px-P.jpg#x']) {
  assert.equal(thumbnailUrl(untouched, 320), untouched);
}
assert.equal(thumbWidthFor({ width: 72, height: 72 }), THUMB_WIDTH);                    // 목록 카드
assert.equal(thumbWidthFor({ width: 76, height: 64 }), THUMB_WIDTH);                    // 갤러리 썸네일
assert.equal(thumbWidthFor({ width: '100%', height: 240 }), undefined);                 // 상세 대표 사진
assert.equal(thumbWidthFor({ width: SMALL_FRAME_PX + 1 }), undefined);
assert.equal(thumbWidthFor({ width: 72 }, 0), undefined);
assert.equal(thumbWidthFor(undefined, 480), 480);

const find = (node, type) => {
  if (!node || typeof node !== 'object') return null;
  if (node.type === type) return node;
  for (const child of [].concat(node.props?.children ?? [])) { const found = find(child, type); if (found) return found; }
  return null;
};
const photo = { url: big, attribution: 'A', license: 'CC BY-SA 4.0', license_url: 'https://creativecommons.org/licenses/by-sa/4.0', keep_aspect_ratio: true, width: 3000 };
const card = find(PlacePhoto({ photo, fit: 'cover', style: { width: 72, height: 72 }, label: '장소' }), 'img');
assert.ok(card, '웹은 <img> 하나로 그린다');
assert.equal(card.props.src, thumbnailUrl(big, THUMB_WIDTH));
assert.equal(card.props.loading, 'lazy');
assert.equal(card.props.decoding, 'async');
assert.equal(card.props.alt, '장소');
assert.equal(card.props.style.objectFit, 'cover');
assert.equal(card.props['data-testid'], 'place-photo-image');
const hero = find(PlacePhoto({ photo, style: { width: '100%', height: 240 } }), 'img');
assert.equal(hero.props.src, big);                                                      // 상세 대표 사진은 원래 크기
assert.equal(hero.props.style.objectFit, 'contain');
const nd = { ...photo, license: 'CC BY-ND 4.0', license_url: 'https://creativecommons.org/licenses/by-nd/4.0' };
const ndImage = find(PlacePhoto({ photo: nd, fit: 'cover', style: { width: 72, height: 72 } }), 'img');
assert.equal(ndImage.props.style.objectFit, 'contain');                                 // 변경 금지 사진은 자르지 않는다
assert.equal(ndImage.props.src, thumbnailUrl(big, THUMB_WIDTH));                        // 크기 조정은 위키미디어 썸네일: 자르기 아님
assert.equal(find(PlacePhoto({ photo: null, style: { width: 72 } }), 'img'), null);
platform.OS = 'ios';
const native = find(PlacePhoto({ photo, fit: 'cover', style: { width: 72, height: 72 } }), 'Image');
assert.equal(native.props.source.uri, thumbnailUrl(big, THUMB_WIDTH));
assert.equal(find(PlacePhoto({ photo, style: { width: 72 } }), 'img'), null);
console.log('place-photo thumbnails ok');
