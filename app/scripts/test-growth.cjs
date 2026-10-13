// Exercise preview persistence without touching the user's browser or contacting a service.
const assert=require('node:assert/strict');
const fs=require('node:fs');
const path=require('node:path');
const vm=require('node:vm');
const ts=require('typescript');
const root=path.resolve(__dirname,'..');
const values=new Map();
const moduleCache=new Map();
let previewFetch=()=>{throw new Error('Preview tests must not use the network');};
function load(file) {
  if(moduleCache.has(file))return moduleCache.get(file).exports;
  if(file.endsWith('.json'))return JSON.parse(fs.readFileSync(file,'utf8'));
  const output=ts.transpileModule(fs.readFileSync(file,'utf8'),{compilerOptions:{module:ts.ModuleKind.CommonJS,target:ts.ScriptTarget.ES2022,esModuleInterop:true}}).outputText;
  const mod={exports:{}};moduleCache.set(file,mod);
  vm.runInNewContext(output,{module:mod,exports:mod.exports,require:name=>load(path.resolve(path.dirname(file),name.endsWith('.json')?name:name+'.ts')),
    process:{env:{}},URL,Response,Date,console,crypto:require('node:crypto').webcrypto,
    localStorage:{getItem:key=>values.get(key)??null,setItem:(key,value)=>values.set(key,value),removeItem:key=>values.delete(key)},
    fetch:(...args)=>previewFetch(...args)}, {filename:file});
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

  // The real demo adapter must preserve all saved IDs while respecting the API's 100-ID bound.
  let batches=[];
  previewFetch=async(url,init)=>{
    assert.equal(url,'/preview/evaluate');
    const ids=JSON.parse(init.body).place_ids;
    assert.ok(ids.length>0 && ids.length<=100);
    batches.push(ids);
    const places=Object.fromEntries([...ids,'nearby-unsaved'].map(id=>[id,{name:id,address:null,photos:[]}]));
    return new Response(JSON.stringify({places}));
  };
  for(const count of [100,101,205]) {
    await call('/me','DELETE');
    batches=[];
    assert.deepEqual(await (await call('/me/bookmarks')).json(),[]);
    assert.equal(batches.length,0);                         // Empty lists need no catalog request.
    const ids=Array.from({length:count},(_,i)=>`saved-${i}`);
    for(const id of ids)await call('/me/bookmarks/'+id,'PUT');
    const response=await call('/me/bookmarks');
    assert.equal(response.status,200);
    assert.deepEqual((await response.json()).map(p=>p.place_id),ids);
    assert.deepEqual(batches.flat(),ids);                   // Complete list, original order, no nearby extras.
  }
  const successfulFetch=previewFetch;
  batches=[];
  previewFetch=(...args)=>batches.length===1 ? new Response('{}',{status:503}) : successfulFetch(...args);
  assert.equal((await call('/me/bookmarks')).status,503);    // Never pass off a partial list as complete.
  previewFetch=successfulFetch;
  batches=[];
  assert.equal((await (await call('/me/bookmarks')).json()).length,205);
  await call('/me/bookmarks/saved-204','DELETE');
  assert.equal((await (await call('/me/bookmarks')).json()).length,204);
  const abort=new AbortController();
  batches=[];
  previewFetch=async(...args)=>{const result=await successfulFetch(...args);abort.abort();return result;};
  await assert.rejects(()=>demoFetch('https://local.invalid/v1/me/bookmarks',{signal:abort.signal}),{name:'AbortError'});
  assert.equal(batches.length,1);                          // Cancellation stops subsequent batches.
  console.log('Preview bookmark regressions passed: 100/101/205 saves, order, failure, retry, deletion and cancellation.');
  const calls=[];
  previewFetch=async(url,init)=>{
    calls.push([url,init]);
    return new Response(JSON.stringify(url.endsWith('/session') ? {ok:true} : {photo_id:'photo',liked:true,like_count:2}));
  };
  const vote=await call('/places/place/photo-likes','POST',{photo_id:'photo',liked:true});
  assert.equal((await vote.json()).like_count,2);
  assert.deepEqual(calls.map(c=>c[0]),['/preview/photo-likes/session','/preview/photo-likes/place']);
  assert.ok(calls.every(c=>c[1].credentials==='include'));
  assert.deepEqual(JSON.parse(calls[1][1].body),{photo_id:'photo',liked:true});
  calls.length=0;
  previewFetch=async(url,init)=>{calls.push([url,init]);return new Response('{}',{status:503});};
  assert.equal((await call('/places/place/photo-likes','POST',{photo_id:'photo',liked:true})).status,503);
  assert.equal(calls.length,1);
  console.log('Preview photo likes reach the shared server with cookies and stop on a failed session.');

  const profile={gender:'female',birth_year:1993,height_cm:168.5,pc_season:'summer_cool',pc_subtone:'light',body_type:'wave',mbti:'INFP'};
  const saju={percents:{wood:20,fire:0,earth:20,metal:30,water:30},dominant_element:'fire'};
  previewFetch=async(url,init)=>new Response(JSON.stringify(url.endsWith('/profile')?JSON.parse(init.body):saju));
  await call('/me/profile','PUT',profile);
  await call('/me/saju','PUT',{birth_date:'1993-08-21',consent:true});
  const before=JSON.parse(values.get('photospot.personal-preview.v1'));
  assert.ok(before.profile && before.saju);
  // Slow saves started before reset cannot bring old personal information back.
  const pending=[];
  previewFetch=()=>new Promise(resolve=>pending.push(resolve));
  const lateProfile=call('/me/profile','PUT',profile);
  const lateSaju=call('/me/saju','PUT',{birth_date:'1993-08-21',consent:true});
  assert.equal((await call('/me/profile','DELETE')).status,204);
  pending[0](new Response(JSON.stringify(profile)));
  pending[1](new Response(JSON.stringify(saju)));
  assert.equal((await lateProfile).status,401);
  assert.equal((await lateSaju).status,401);
  const cleared=await (await call('/me/profile')).json();
  assert.equal(cleared.profile_exists,false);
  assert.equal(cleared.gender,'undisclosed');
  for(const key of ['birth_year','height_cm','pc_season','pc_subtone','body_type','mbti','saju_element','saju_percents']) assert.equal(cleared[key],null);
  assert.equal(cleared.saju_enabled,false);
  const stored=JSON.parse(values.get('photospot.personal-preview.v1'));
  assert.equal(stored.profile,null);
  assert.equal(stored.saju,null);
  assert.deepEqual(stored.bookmarks,before.bookmarks);
  assert.equal((await call('/me/profile','DELETE')).status,204); // Retry is safe.
  console.log('Start over clears all profile/saju fields, preserves bookmarks and blocks stale saves.');
})().catch(error=>{console.error(error);process.exitCode=1;});
