// Exercise the real React lifecycle without a browser, router or network.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

const file = path.resolve(__dirname, '../src/hooks.ts');
const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText;
const mod = { exports: {} };
vm.runInNewContext(output, { module: mod, exports: mod.exports, require: (name) => {
  if (name === 'react') return React;
  if (name === 'expo-router') return { useFocusEffect() {} };
  if (name === '@photospot/client') return { ApiError: class extends Error {} };
  throw new Error(`Unexpected import: ${name}`);
} }, { filename: file });
const { useAsync } = mod.exports;
function deferred() {
  let resolve, reject;
  const promise = new Promise((yes, no) => { resolve = yes; reject = no; });
  return { promise, resolve, reject };
}

(async () => {
  const requests = [], renders = [];
  let value, renderer;
  function Probe({ location, date = '2026-10-12', revision = 0 }) {
    value = useAsync(() => {
      const request = deferred();
      requests.push({ location, date, ...request });
      return request.promise;
    }, [location, date], revision);
    renders.push({ location, date, ...value });
    return null;
  }
  const update = (props) => act(() => renderer.update(React.createElement(Probe, props)));
  await act(() => { renderer = create(React.createElement(Probe, { location: 'Seoul' })); });
  await act(() => requests[0].resolve('Seoul recommendations'));
  assert.equal(value.data, 'Seoul recommendations');

  // Hide old results on the very first render with a different query, even before effects run.
  const firstChangedRender = renders.length;
  await update({ location: 'Busan' });
  assert.equal(renders[firstChangedRender].data, null);
  assert.equal(value.data, null);
  assert.equal(value.loading, true);
  await act(() => requests[1].reject(new Error('offline')));
  assert.equal(value.data, null);
  assert.equal(value.error.message, 'offline');
  assert.equal(value.loading, false);

  // Retry the current query; refocusing with unchanged conditions keeps its result.
  await act(() => value.reload());
  await act(() => requests[2].resolve('Busan recommendations'));
  await update({ location: 'Busan', revision: 1 });
  assert.equal(value.data, 'Busan recommendations');
  assert.equal(value.loading, true);
  await act(() => requests[3].resolve('Updated Busan recommendations'));
  assert.equal(value.data, 'Updated Busan recommendations');

  // Date changes also clear results, and late responses cannot replace the latest query.
  await update({ location: 'Busan', date: '2026-10-13', revision: 1 });
  assert.equal(value.data, null);
  await update({ location: 'Gangneung', date: '2026-10-13', revision: 1 });
  await act(() => requests[5].resolve('Gangneung recommendations'));
  await act(() => requests[4].resolve('Stale Busan recommendations'));
  assert.equal(value.data, 'Gangneung recommendations');
  assert.equal(value.error, null);
  await act(() => renderer.unmount());
  console.log('Async hook regressions passed: query changes, failure, retry, refocus and late responses.');
})().catch((error) => { console.error(error); process.exitCode = 1; });
