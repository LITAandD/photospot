// Exercise preview persistence without touching the user's browser or contacting a service.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const root=path.resolve(__dirname,'..');
const values=new Map();
const moduleCache=new Map();
function load(file) {
  if(moduleCache.has(file))return moduleCache.get(file).exports;
  if(file.endsWith('.json'))return JSON.parse(fs.readFileSync(file,'utf8'));
  const output=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
  const mod={exports:{}};moduleCache.set(file,mod);
  vm.runInNewContext(output,{module:mod,exports:mod.exports,require:name=>load(path.resolve(path.dirname(file),name.endsWith('.json')?name:name+'.ts')),
    process:{env:{}},URL,Response,Date,console,crypto:require('node:crypto').webcrypto,
    localStorage:{getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)},
    fetch:()=>{throw new Error('Preview tests must not use the network');}}, {filename:file});
  return mod.exports;
}
(async()=>{
  const {demoFetch}=load(path.join(root,'src/demo/fetch.ts'));
  const call=(path,method='GET',body)=>demoFetch('https://local.invalid/v1'+path,{method,...(body?{body:JSON.stringify(body)}:{})});
  assert.equal((await (await call('/me/session')).json()).ai_configured,false);
  assert.deepEqual((await (await call('/auth/providers')).json()).providers,[]);
  assert.equal((await call('/feedback','POST',{category:'bug',message:'    '})).status,422);
  const created=await (await call('/feedback','POST',{category:'idea',message:'[자동검증] 추천 화면 개선',ai_consent:true})).json();
  assert.equal((await (await call('/me/feedback')).json()).length,1);
  assert.equal((await call('/admin/feedback/'+created.id,'PATCH',{reviewed_text:'개인정보 없는 기능 제안'})).status,204);
  assert.equal((await (await call('/admin/feedback')).json())[0].reviewed_text,'개인정보 없는 기능 제안');
  assert.equal((await call('/admin/feedback/triage','POST',{feedback_ids:[created.id]})).status,503);
  assert.equal((await call('/me/billing/sync','POST')).status,503);
  await call('/me/feedback/'+created.id,'DELETE');
  assert.equal((await (await call('/me/feedback')).json()).length,0);
  assert.deepEqual(await (await call('/sponsorships')).json(),[]);
  console.log('Preview feedback submit/review/delete and external-service isolation passed.');
})().catch(error=>{console.error(error);process.exitCode=1;});
