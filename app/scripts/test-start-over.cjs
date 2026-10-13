// Test the real button: failed resets keep the session and a retry cannot double-submit.
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
  if (name === '@/components/ui') return { ErrorBox: 'ErrorBox' };
  if (name === '@/hooks') return { errorMessage: e => e.message };
  if (name === '@/theme') return { colors: {}, fonts: {} };
  throw new Error(name);
} });
(async () => {
  let tree;
  await act(() => { tree = create(React.createElement(mod.exports.StartOver)); });
  const button = () => tree.root.findByType('Pressable');
  const press = button().props.onPress;
  await act(() => { press(); press(); });
  assert.equal(requests.length, 1);
  assert.equal(button().props.disabled, true);
  assert.equal(events.length, 0);
  await act(() => requests[0].reject(new Error('연결 오류')));
  assert.equal(button().props.disabled, false);
  assert.equal(tree.root.findByType('ErrorBox').props.message, '연결 오류');
  assert.equal(events.length, 0);
  await act(() => { tree.root.findByType('ErrorBox').props.onRetry(); });
  await act(() => requests[1].resolve());
  assert.deepEqual(events, ['reset', '/', 'logout', 'consumed']);
  assert.equal(tree.root.findAllByType('ErrorBox').length, 0);
  await act(() => tree.unmount());
  console.log('Start over: duplicate clicks blocked, failed reset stays signed in, retry clears draft before landing navigation.');
})().catch(e => { console.error(e); process.exitCode = 1; });
