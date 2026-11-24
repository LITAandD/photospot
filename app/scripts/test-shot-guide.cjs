const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const file = path.resolve(__dirname, '../src/shot-guide.ts');
function load(fetch) {
  const mod = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { exports: mod.exports, module: mod, process: { env: {} },
    URLSearchParams, AbortController, setTimeout, clearTimeout, Error, TypeError, fetch });
  return mod.exports;
}
(async () => {
  const query = { date: '2026-11-24', party: '', goal: '', time: '', cut: 'gbg-01', review: '' };
  const calls = [];
  const api = load(async (url, init) => { calls.push({url, init}); return {ok:true,json:async()=>({mode:'catalog'})}; });
  const shared = api.shotParams(query);
  assert.equal(shared.get('date'), query.date);
  assert.equal(shared.get('city'), 'seoul');
  assert.equal(shared.get('cut'), 'gbg-01');
  assert.equal(shared.has('party'), false);
  assert.equal((await api.fetchShots(query)).mode, 'catalog');
  assert.equal(calls[0].init.credentials, 'same-origin');
  assert.equal(calls[0].url, '/preview/shots?visit_date=2026-11-24&cut=gbg-01');
  assert.equal(calls[0].init.headers, undefined); // no app token
  await assert.rejects(load(async()=>{throw new TypeError('Failed to fetch')}).fetchShots(query), /인터넷 연결/);
  const timeout = new Error('timeout'); timeout.name='AbortError';
  await assert.rejects(load(async()=>{throw timeout}).fetchShots(query), /지연/);
  await assert.rejects(load(async()=>({ok:false,status:404})).fetchShots(query), /컷 선택을 해제/);
  console.log('shot guide: shared context, optional inputs, preview access and network errors passed');
})().catch(e => { console.error(e); process.exit(1); });
