import React, { useState } from 'react';
import { TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import type { AppFeedback, Triage, Campaign } from '@photospot/client';
import { api, DEMO } from '@/api';
import { Body, Button, Card, Chip, ErrorBox, Field, Muted, Screen, Title } from '@/components/ui';
import { errorMessage, useAsync } from '@/hooks';
import { colors } from '@/theme';

const editStyle={minHeight:90,padding:12,borderWidth:1,borderColor:colors.line,borderRadius:12,color:colors.ink,backgroundColor:colors.card};
function Review({item,save,busy}:{item:AppFeedback;save:(text:string)=>void;busy:boolean}) {
  const [text,setText]=useState(item.reviewed_text ?? item.message);
  return <Card><Body>{item.category} · {new Date(item.created_at).toLocaleDateString('ko-KR')}</Body><Muted>{item.message}</Muted>
    {item.ai_consent?<><TextInput accessibilityLabel="개인정보 제거 후 분석할 의견" multiline style={editStyle} value={text} maxLength={2000} onChangeText={setText}/><Muted size={12}>이름·주소·계정·연락처 등 식별 정보를 직접 확인하고 제거해 주세요.</Muted><Button title={item.reviewed_text?'개인정보 검토 내용 갱신':'개인정보 검토 완료'} variant="outline" disabled={busy||text.trim().length<5} onPress={()=>save(text)}/></>:<Muted>AI 분석 미동의 · 개발자가 직접 검토하세요.</Muted>}
  </Card>;
}
function Decision({item,save,busy}:{item:Triage;save:(status:Exclude<Triage['status'],'proposed'>,note:string)=>void;busy:boolean}) {
  const [note,setNote]=useState('');
  const next = ({proposed:'approved',approved:'planned',planned:'done'} as const)[item.status as 'proposed'|'approved'|'planned'];
  const names={proposed:'검토 대기',approved:'승인',planned:'개발 계획',done:'완료',dismissed:'보류'};
  return <Card><Body>{item.result.title} · {names[item.status]}</Body><Body>우선순위 {item.result.priority_score} · 제보자 {item.result.reporters}명</Body><Muted>{item.result.summary}</Muted><Muted>영향 {item.result.impact}/5 · 긴급도 {item.result.urgency}/5 · 예상 노력 {item.result.effort}/5</Muted><Muted>{item.result.reason}</Muted><Body>완료 기준</Body><Muted>{item.result.acceptance}</Muted>
    {item.review_note?<Muted>개발자: {item.review_note}</Muted>:null}
    {next?<><TextInput accessibilityLabel="개선안 검토 메모" style={editStyle} multiline value={note} maxLength={1000} onChangeText={setNote} placeholder="승인 이유·작업 계획·검증 결과"/><Button title={names[next]+'으로 변경'} disabled={busy||note.trim().length<3} onPress={()=>save(next,note)}/><Button title="보류" variant="outline" disabled={busy||note.trim().length<3} onPress={()=>save('dismissed',note)}/></>:null}
  </Card>;
}
export default function Admin() {
  const router=useRouter(),session=useAsync(()=>api.session(),[]);
  const [tab,setTab]=useState<'feedback'|'ads'>('feedback'),[busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[notice,setNotice]=useState<string|null>(null);
  const data=useAsync(async()=>{const s=await api.session();if(!s.is_admin)throw new Error('관리자 권한이 필요해요');return {feedback:await api.adminFeedback(),triages:await api.adminTriages(),campaigns:await api.adminCampaigns()};},[]);
  const [selected,setSelected]=useState<string[]>([]),[place,setPlace]=useState(''),[sponsor,setSponsor]=useState(''),[headline,setHeadline]=useState(''),[placement,setPlacement]=useState<Campaign['placement']>('priority'),[start,setStart]=useState(''),[end,setEnd]=useState('');
  const run=async(fn:()=>Promise<unknown>,message='저장했어요')=>{if(busy)return;setBusy(true);setError(null);setNotice(null);try{await fn();setNotice(message);data.reload();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}};
  const create=()=>run(async()=>{const id=place.match(/[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}/i)?.[0];if(!id)throw new Error('장소 상세 주소 또는 장소 ID를 입력해 주세요');await api.createCampaign({place_id:id,sponsor,headline,placement,starts_at:new Date(start+'T00:00:00+09:00').toISOString(),ends_at:new Date(end+'T00:00:00+09:00').toISOString()});},'광고 초안을 만들었어요. 목록에서 확인한 뒤 승인해 주세요.');
  return <Screen style={{paddingTop:24}}><Title>운영 관리</Title>{DEMO?<Muted>로컬 관리 화면 미리보기 · 실제 GPT 분석·결제·광고 송출은 실행하지 않아요.</Muted>:null}
    <View style={{flexDirection:'row',gap:8}}><Chip label="피드백 · 개선 순서" selected={tab==='feedback'} onPress={()=>setTab('feedback')}/><Chip label="광고 운영" selected={tab==='ads'} onPress={()=>setTab('ads')}/></View>
    {error?<ErrorBox message={error}/>:null}{notice?<Card><Body>{notice}</Body></Card>:null}{data.error?<ErrorBox message={errorMessage(data.error)} onRetry={data.reload}/>:null}
    {session.data?.is_admin && tab==='feedback'?<><Muted>개인정보 검토 → GPT 요약 → 개발자 승인 → 개발 계획 → 완료 순서예요. AI 제안은 코드나 배포에 자동 반영되지 않아요.</Muted>
      {data.data?.feedback.map(item=><View key={item.id} style={{gap:8}}><Review item={item} busy={busy} save={text=>run(()=>api.reviewFeedback(item.id,text))}/>
        {item.reviewed_text && !data.data?.triages.some(t=>t.result.feedback_ids.includes(item.id))?<Chip label={selected.includes(item.id)?'분석 대상으로 선택됨':'분석 대상 선택'} selected={selected.includes(item.id)} onPress={()=>setSelected(old=>old.includes(item.id)?old.filter(x=>x!==item.id):[...old,item.id].slice(0,20))}/>:null}</View>)}
      {!data.data?.feedback.length?<Card><Body>접수된 의견이 없어요</Body><Muted>이용자가 보낸 의견이 여기에 모여요.</Muted></Card>:null}
      <Button title={`GPT로 ${selected.length}건 요약·우선순위 제안`} disabled={busy||!selected.length||!session.data.ai_configured||DEMO} onPress={()=>run(async()=>{await api.triageFeedback(selected);setSelected([]);},'개선 제안을 만들었어요. 개발자가 근거와 완료 기준을 검토해 주세요.')}/>
      {!session.data.ai_configured?<Muted>서버의 OpenAI API 설정이 필요해요. 검토 내용은 저장할 수 있어요.</Muted>:null}
      <Muted size={12}>우선순위 = (영향×3 + 긴급도×2 + 제보자 수[최대 5]) ÷ 예상 노력. AI의 추정값이므로 개발자가 검토해 주세요. 분석은 한 번에 20건, 하루 20회까지예요.</Muted>
      {data.data?.triages.map(item=><Decision key={item.id} item={item} busy={busy} save={(status,note)=>run(()=>api.decideTriage(item.id,status,note))}/>)}
    </>:null}
    {session.data?.is_admin && tab==='ads'?<><Muted>직접 계약한 업체의 광고를 등록해요. 실제 사진이 있는 공개 장소만 가능하고, 승인된 기간에만 노출돼요. 광고비 정산은 계약에 따라 별도로 진행해요.</Muted>
      <Card><Field label="장소 상세 주소 또는 ID" value={place} onChange={setPlace}/><Field label="광고주" value={sponsor} onChange={setSponsor}/><Field label="광고 문구" value={headline} onChange={setHeadline}/>
        <View style={{flexDirection:'row',gap:8}}><Chip label="우선 추천 광고" selected={placement==='priority'} onPress={()=>setPlacement('priority')}/><Chip label="배너 광고" selected={placement==='banner'} onPress={()=>setPlacement('banner')}/></View>
        <Field label="시작일 (YYYY-MM-DD · 한국시간 0시)" value={start} onChange={setStart}/><Field label="종료일 (YYYY-MM-DD · 한국시간 0시)" value={end} onChange={setEnd}/><Button title="검토용 광고 초안 만들기" disabled={busy||DEMO||!place||!sponsor||!headline||!start||!end} onPress={create}/>
      </Card>
      {data.data?.campaigns.map(c=><Card key={c.id}><Body>{c.headline}</Body><Muted>{c.sponsor} · {c.placement==='banner'?'배너':'우선 추천'} · {c.approved?'승인됨':'미승인'}</Muted><Muted>{c.starts_at} ~ {c.ends_at}</Muted><Muted>일별 고유 노출 {c.impressions??0} · 클릭 {c.clicks??0}</Muted><Button title="대상 장소 확인" variant="outline" onPress={()=>router.push({pathname:'/place/[id]',params:{id:c.place_id}})}/><Button title={c.approved?'광고 중지':'검토 완료 · 광고 승인'} disabled={busy} onPress={()=>run(()=>api.approveCampaign(c.id,!c.approved))}/></Card>)}
      <Muted size={12}>지표는 이용자별 하루 1회 집계한 운영 참고치이며 과금·정산 근거로 사용하지 않아요.</Muted>
    </>:null}
    <Button title="설정으로 돌아가기" variant="outline" onPress={()=>router.replace('/settings')}/>
  </Screen>;
}
