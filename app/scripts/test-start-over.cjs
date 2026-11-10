// Test the real button: a confirm card opens first (F021), failed resets keep the session and a retry cannot double-submit.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
const requests = [], events = [];
const file = path.resolve(__dirname, '../src/components/start-over.tsx');
const mod = { exports: {} };
const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText;
vm.runInNewContext(output, { module: mod, exports: mod.exports, require(name) {
  if (name === 'react' || name === 'react/jsx-runtime') return require(name);
  if (name === 'react-native') return Object.fromEntries(['ActivityIndicator','Pressable','Text','View'].map(n=>[n,n]));
  if (name === '@/api') return { api: {
    resetProfile: () => new Promise((resolve, reject) => requests.push({ resolve, reject })),
    auth: { logout: async () => events.push('logout') },
  } };
  if (name === '@/state/onboarding') return { useOnboarding: () => ({ dispatch: action => events.push(action.type) }) };
  if (name === '@/state/sign-out') return { signOutTo: route => events.push(route), takeSignOutRoute: () => events.push('consumed') };
  if (name === '@/components/ui') return Object.fromEntries(['Button', 'Card', 'ErrorBox', 'Muted', 'Title'].map(n => [n, n]));
  if (name === '@/hooks') return { errorMessage: e => e.message };
  if (name === '@/theme') return { colors: {}, fonts: {} };
  throw new Error(name);
} });
(async () => {
  let tree;
  await act(() => { tree = create(React.createElement(mod.exports.StartOver)); });
  const trigger = () => tree.root.findByType('Pressable');
  const confirm = () => tree.root.findAllByProps({ testID: 'start-over-confirm' }).filter(n => n.type === 'View');
  const button = (title) => tree.root.findAllByType('Button').find(b => b.props.title === title);
  // Nothing is deleted before the confirm card is open; the trigger exposes expanded state for the web (aria-expanded).
  assert.equal(confirm().length, 0);
  assert.equal(trigger().props['aria-expanded'], false);
  await act(() => { trigger().props.onPress(); });
  assert.equal(requests.length, 0);
  assert.equal(confirm().length, 1);
  assert.equal(confirm()[0].props.role, 'alertdialog');
  assert.equal(trigger().props['aria-expanded'], true);
  const copy = JSON.stringify(tree.toJSON());
  for (const word of ['프로필', '사주', '로그아웃', '저장한 장소는 계정에 남']) assert.ok(copy.includes(word), word);
  // Cancel closes without a request.
  await act(() => { button('취소').props.onPress(); });
  assert.equal(confirm().length, 0);
  assert.equal(requests.length, 0);
  // Confirm: duplicate taps make one request, the trigger and buttons lock while busy.
  await act(() => { trigger().props.onPress(); });
  const press = button('초기화하고 처음으로').props.onPress;
  await act(() => { press(); press(); });
  assert.equal(requests.length, 1);
  assert.equal(trigger().props.disabled, true);
  assert.equal(trigger().props['aria-busy'], true);
  assert.equal(button('초기화하고 처음으로').props.loading, true);
  assert.equal(button('취소').props.disabled, true);
  assert.equal(events.length, 0);
  await act(() => requests[0].reject(new Error('연결 오류')));
  assert.equal(trigger().props.disabled, false);
  assert.equal(tree.root.findByType('ErrorBox').props.message, '연결 오류');
  assert.equal(confirm().length, 1);                                  // 실패해도 확인 창은 남아 다시 시도할 수 있다
  assert.equal(events.length, 0);
  await act(() => { tree.root.findByType('ErrorBox').props.onRetry(); });
  await act(() => requests[1].resolve());
  assert.deepEqual(events, ['reset', '/', 'logout', 'consumed']);
  assert.equal(tree.root.findAllByType('ErrorBox').length, 0);
  await act(() => tree.unmount());
  console.log('Start over: confirm card lists deletions, cancel is free, duplicate clicks blocked, failed reset stays signed in, retry clears draft before landing navigation.');
})().catch(e => { console.error(e); process.exitCode = 1; });
