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
  const entryCalls=[];
  await load(async(url,init)=>{entryCalls.push({url,init});return {ok:true,json:async()=>({date:query.date,entry_ready:false,mode:'catalog'})}}).fetchShotEntry(query.date);
  assert.equal(entryCalls[0].url,'/preview/shots?visit_date=2026-11-24&view=entry');
  let starts=0,aborts=0;
  const cancellable=load((_url,init)=>new Promise((_resolve,reject)=>{
    starts++;init.signal.addEventListener('abort',()=>{aborts++;reject(Object.assign(new Error('cancelled'),{name:'AbortError'}))},{once:true});
  }));
  const owner=new AbortController();
  const inflight=cancellable.fetchShots(query,owner.signal);owner.abort();
  await assert.rejects(inflight,e=>e.name==='AbortError'&&!e.message.includes('지연'));
  assert.equal(aborts,1);
  await assert.rejects(cancellable.fetchShotEntry(query.date,owner.signal),e=>e.name==='AbortError');
  assert.equal(starts,1,'already cancelled request never starts');
  console.log('shot guide: shared context, optional inputs, preview access and network errors passed');
})().catch(e => { console.error(e); process.exit(1); });

{
const assert=require('node:assert/strict'),fs=require('node:fs'),vm=require('node:vm'),ts=require('typescript');
const mod={exports:{}},store=new Map();
const context={module:mod,exports:mod.exports,URLSearchParams,Map,JSON,process:{env:{}},sessionStorage:{getItem:k=>store.get(k),setItem:(k,v)=>store.set(k,v)}};
vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/shot-guide.ts'),'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022}}).outputText,context);
const g=mod.exports;
for(const [input,expected]of [['9:30','09:30'],['1530','15:30'],['00:00','00:00'],['2359','23:59'],['25:00',null],['1260',null],['1',null],['','']])assert.equal(g.normalizeShotTime(input),expected);
assert.equal(g.bearingLabel(0),'북쪽(0°)');assert.equal(g.bearingLabel(45),'북동쪽(45°)');assert.equal(g.bearingLabel(359),'북쪽(359°)');
g.writeShotDone(['gbg-01/2026-11-24']);assert.equal(g.readShotDone()[0],'gbg-01/2026-11-24');
context.sessionStorage={getItem(){throw Error('blocked')},setItem(){throw Error('blocked')}};
assert.equal(g.readShotDone().length,0);assert.doesNotThrow(()=>g.writeShotDone(['x']));
assert.match(g.shotEmptyReasons({candidate_count:20,excluded:[{code:'pending',reason:'pending'}]})[0],/확인 중/);
assert.equal(g.shotEmptyReasons({excluded:[{code:'closed',reason:'선택일 정기 휴무'}]})[0],'선택일 정기 휴무 · 1컷');
assert.equal(g.shotEmptyReasons({excluded:[{code:'purpose',reason:'유형 불일치'}]})[0],'유형 불일치 · 1컷');
console.log('Shot UI helpers: input commit, direction, reload completion, denied storage and precise empty reasons pass.');

}
