// Exercise the actual gallery lifecycle: retries, double clicks and reordering.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
const file = path.resolve(__dirname, '../src/components/place-gallery.tsx');
const mod = { exports: {} };
const requests = [];
const api = { setPhotoLike: (...args) => new Promise((resolve, reject) => requests.push({ args, resolve, reject })) };
const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText;
vm.runInNewContext(output, { module: mod, exports: mod.exports, require(name) {
  if (name === 'react' || name === 'react/jsx-runtime') return require(name);
  if (name === 'react-native') return { Pressable: 'Pressable', ScrollView: 'ScrollView', View: 'View' };
  if (name === '@/components/ui') return Object.fromEntries(['Body', 'Button', 'ErrorBox', 'Label', 'Muted'].map(n => [n,n]));
  if (name === '@/components/place-photo') return { PlacePhoto: 'PlacePhoto', PhotoCredit: 'PhotoCredit' };
  if (name === '@/api') return { api };
  if (name === '@/hooks') return { errorMessage: e => e.message };
  if (name === '@/theme') return { colors: { accent: 'red', line: 'gray' } };
  throw new Error(name);
} });
const { PlaceGallery } = mod.exports;
(async () => {
  const a = { url: 'a', photo_id: 'a', like_count: 0, liked: false, likes_enabled: true };
  const b = { ...a, url: 'b', photo_id: 'b' };
  let reloads = 0, tree;
  const props = { placeId: 'place', photos: [a, b], onLiked: () => reloads++ };
  await act(() => { tree = create(React.createElement(PlaceGallery, props)); });
  const button = () => tree.root.findByProps({ testID: 'photo-like' });
  const choose = () => tree.root.findByProps({ title: '다음 사진' }).props.onPress();
  await act(choose);
  const press = button().props.onPress;
  await act(() => { press(); press(); });
  assert.equal(requests.length, 1);
  assert.deepEqual([...requests[0].args], ['place', 'b', true]);
  assert.equal(button().props.disabled, true);
  await act(() => requests[0].reject(new Error('offline')));
  assert.equal(reloads, 0);
  assert.equal(button().props['aria-pressed'], false);
  assert.equal(tree.root.findByType('ErrorBox').props.message, 'offline');
  await act(() => { button().props.onPress(); });
  await act(() => requests[1].resolve({ photo_id: 'b', liked: true, like_count: 1 }));
  assert.equal(reloads, 1);
  assert.equal(button().props['aria-pressed'], true);
  await act(() => tree.update(React.createElement(PlaceGallery, { ...props, photos: [{ ...b, liked: true, like_count: 1 }, a] })));
  assert.equal(tree.root.findAllByType('PlacePhoto')[0].props.photo.url, 'b');
  assert.equal(button().props['aria-pressed'], true);
  await act(() => { button().props.onPress(); });
  assert.deepEqual([...requests[2].args], ['place', 'b', false]);
  await act(() => requests[2].resolve({ photo_id: 'b', liked: false, like_count: 0 }));
  assert.equal(button().props['aria-pressed'], false);
  await act(() => tree.unmount());
  console.log('Photo likes: real gallery duplicate-click guard, failed save, retry, unlike, selected photo after ranking passed.');
})().catch(e => { console.error(e); process.exitCode = 1; });
