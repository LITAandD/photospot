import React, { useCallback, useEffect, useRef, useState } from 'react';
import { ActivityIndicator, Linking, Platform, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { DEMO, today } from '@/api';
import { track } from '@/analytics';
import { validCalendarDate } from '@/calendar';
import { useAsync, useDocumentTitle } from '@/hooks';
import { Body, Button, Card, Chip, ErrorBox, Field, Muted, Screen, Title } from '@/components/ui';
import { CalendarField } from '@/components/calendar-field';
import { ShotCard } from '@/components/shot-card';
import { fetchShots, normalizeShotTime, readShotDone, shotEmptyReasons, shotParams, writeShotDone, type Shot, type ShotQuery } from '@/shot-guide';
import { shareText, shareUrl, SHARE_NOTICE } from '@/share';

const first = (v: string | string[] | undefined) => Array.isArray(v) ? v[0] : v ?? '';
const CASES = [['open', '정상 개방'], ['weekly_closed', '정기 휴무'], ['cutoff', '입장마감 전후'], ['temporary_closed', '임시 통제'], ['unknown', '운영정보 미확인'], ['no_alternative', '대체 컷 없음']];
const PARTIES = [['solo','혼자'],['pair','둘이'],['family','가족']];
const GOALS = [['portrait','인물'],['architecture','건축'],['landscape','풍경']];

export default function TodayShot() {
  const router = useRouter(), params = useLocalSearchParams();
  const date = validCalendarDate(first(params.date)) ? first(params.date) : today();
  const party = first(params.party), goal = first(params.goal);
  const query: ShotQuery = { date, party: ['solo','pair','family'].includes(party) ? party as ShotQuery['party'] : '',
    goal: ['portrait','architecture','landscape'].includes(goal) ? goal as ShotQuery['goal'] : '',
    time: first(params.time), cut: first(params.cut), review: first(params.review) };
  const key = shotParams(query).toString();
  const validTime = !query.time || /^([01]\d|2[0-3]):[0-5]\d$/.test(query.time);
  const past = date < today();
  const result = useAsync(signal => DEMO && validTime && !past ? fetchShots(query,signal).then(payload => ({...payload, request_key:key})) : Promise.resolve(null), [key,validTime,past]);
  const data = !result.loading && !result.error && result.data?.request_key === key ? result.data : null;
  const [notice,setNotice] = useState(''), [conditions,setConditions] = useState(false), [reviewMenu,setReviewMenu] = useState(false);
  const [draftTime,setDraftTime] = useState(query.time), [timeError,setTimeError] = useState(false);
  const [done,setDone] = useState<string[]>(() => Platform.OS === 'web' ? readShotDone() : []);
  const viewed = useRef(new Set<string>()), focusAfter = useRef(false), resultFocus = useRef<View>(null);
  useDocumentTitle(data?.primary ? `오늘의 한 컷 · ${data.primary.title} · ${data.primary.place_name} · 포토스팟` : '오늘의 한 컷 · 광화문·정동 · 포토스팟');
  useEffect(() => {setDraftTime(query.time);setTimeError(!validTime);},[query.time,validTime]);
  useEffect(() => {
    if (!data || data.mode !== 'catalog' || viewed.current.has(key)) return;
    viewed.current.add(key);
    void track('shot_view',{result:data.primary?'primary':data.alternative?'alternative_available':'empty',cut_id:data.primary?.cut_id ?? data.alternative?.cut_id ?? null},'/today-shot');
  },[key,data]);
  useEffect(() => {
    if (result.loading || !focusAfter.current) return;
    focusAfter.current=false;
    const node = resultFocus.current as unknown as {focus?:()=>void;scrollIntoView?:(v:object)=>void};
    node?.focus?.(); node?.scrollIntoView?.({block:'start'});
  },[data,result.loading,result.error]);
  const change = (patch: Record<string,string>, focus=false) => {setNotice('');focusAfter.current=focus;router.setParams(patch);};
  const commitTime = () => {
    const value=normalizeShotTime(draftTime);setTimeError(value===null);
    if(value!==null){setDraftTime(value);if(value!==query.time)change({time:value});}
  };
  const event = useCallback((name:'shot_directions'|'shot_alternative'|'shot_completed',cut:string,outcome:string,extra:Record<string,string>={}) => {
    if(data?.mode==='catalog')void track(name,{cut_id:cut,outcome,...extra},'/today-shot');
  },[data?.mode]);
  const navigate = useCallback(async (shot:Shot,provider:'kakao'|'naver'|'google') => {
    if(data?.mode==='review'){setNotice('길찾기 테스트 완료 · 장소 중심점 대신 이 컷의 촬영 핀을 목적지로 사용해요. 실제 지도는 열지 않았어요.');return;}
    try{await Linking.openURL(shot.navigation[provider]);event('shot_directions',shot.cut_id,'opened',{provider});
      if(provider==='naver')setNotice('네이버 앱이 열리지 않으면 카카오맵 웹 길찾기를 이용해 주세요.');}
    catch{setNotice('지도를 열지 못했어요. 카카오맵 웹 길찾기를 다시 확인해 주세요.');}
  },[data?.mode,event]);
  const share = useCallback(async (shot:Shot) => {
    const origin=typeof window!=='undefined'?window.location.origin:'https://photospot.litaandd.com';
    const localOrPreview=typeof window!=='undefined' && (['localhost','127.0.0.1'].includes(window.location.hostname)||window.location.hostname.endsWith('.vercel.app'));
    const parameters=shotParams({...query,cut:shot.cut_id});
    const url=data?.mode==='review'||localOrPreview?`${origin}/today-shot?${parameters}`:shareUrl('/today-shot','share',{...Object.fromEntries(parameters),utm_medium:'today_shot'});
    const outcome=await shareText({title:`${shot.title} · 오늘의 한 컷`,lines:[`오늘의 한 컷 · ${shot.title}`,data?.mode==='review'?'기능 검수용 합성 예시 · 현장 안내 아님':shot.place_name,date],url});
    setNotice(SHARE_NOTICE[outcome]??'');
    if(data?.mode==='catalog')void track('share_click',{surface:'today_shot',cut_id:shot.cut_id,outcome},'/today-shot');
  },[key,data?.mode]);
  const complete = useCallback((shot:Shot) => {
    const id=`${shot.cut_id}/${date}`;if(done.includes(id))return;
    const next=[...done,id];setDone(next);if(Platform.OS==='web')writeShotDone(next);
    event('shot_completed',shot.cut_id,'reported');
    setNotice(data?.mode==='review'?'테스트 완료 · 실제 촬영 집계에는 포함하지 않았어요.':'고마워요. 사진이나 위치는 수집하지 않아요.');
  },[done,date,data?.mode,event]);
  const summary=[date,PARTIES.find(([v])=>v===query.party)?.[1],GOALS.find(([v])=>v===query.goal)?.[1],query.time?`${query.time} 한국시간`:'시간 미선택'].filter(Boolean).join(' · ');
  const status=result.loading?'촬영 조건 확인 중':past?'공유된 날짜가 지났어요':result.error?'촬영 안내를 확인하지 못했어요':data?.primary?`추천 컷: ${data.primary.title}`:data?.replacement_reason?`선택한 컷 이용 불가 · ${data.replacement_reason}`:data?.empty_message??'';
  if(!DEMO)return <Screen><Title headingLevel={1}>오늘의 한 컷</Title><Muted>이 기능은 포토스팟 공개 웹에서 준비 중이에요.</Muted><Button title="서울 둘러보기로" variant="outline" onPress={()=>router.push('/browse')}/></Screen>;
  return <Screen style={{gap:14}}>
    <Button title="서울 둘러보기로" variant="outline" onPress={()=>router.push({pathname:'/browse',params:{city:'seoul',date}})}/>
    <View style={{gap:5}}><Title headingLevel={1} size={30}>오늘의 한 컷</Title><Muted>광화문·정동 · 로그인과 프로필 없이 이용해요.</Muted><Body>{summary}</Body></View>
    <View role="status" accessibilityLiveRegion="polite" aria-live="polite" testID="shot-status"><Muted>{notice||status}</Muted></View>
    {query.review?<Muted size={13}>검토용 합성 예시 · 현장 안내 아님</Muted>:null}
    <View ref={resultFocus} tabIndex={-1} testID="shot-result" style={{gap:12}}>
      {past?<Card><Title headingLevel={2} size={22}>공유된 날짜가 지났어요</Title><Muted>원래 날짜를 유지하고 있어요. 지난 날짜의 촬영 가능 여부는 안내하지 않아요.</Muted><Button title="오늘 날짜로 변경" onPress={()=>change({date:today()},true)}/></Card>:null}
      {result.loading?<View accessibilityRole="progressbar" accessibilityLabel="촬영 조건 확인 중"><ActivityIndicator/></View>:null}
      {result.error?<ErrorBox message={result.error instanceof Error?result.error.message:'촬영 안내 확인에 실패했어요.'} onRetry={result.reload}/>:null}
      {data?.replacement_reason?<Card><Title headingLevel={2} size={22}>선택한 컷을 이용할 수 없어요</Title><Body>{data.replacement_reason}</Body>{data.alternative?<><Muted>같은 사진 목적의 대체 컷 · {data.alternative.place_name}</Muted><Body>{data.alternative.title}</Body><Button title="대체 컷 열기" onPress={()=>{event('shot_alternative',data.alternative!.cut_id,'opened',{from_cut_id:query.cut});change({cut:data.alternative!.cut_id},true);}}/></>:null}</Card>:null}
      {data?.primary?<><Muted>추천 한 컷 · {date}{query.time?` ${query.time}`:''}</Muted><ShotCard key={data.primary.cut_id} shot={data.primary} review={data.mode==='review'} completed={done.includes(`${data.primary.cut_id}/${date}`)} onNavigate={navigate} onShare={share} onComplete={complete}/></>:null}
      {data?.empty_message?<Card><Title headingLevel={2} size={22}>{data.empty_message}</Title>{shotEmptyReasons(data).map(line=><Muted key={line}>{line}</Muted>)}{data.excluded.some(e=>e.code==='purpose')?<Button title="사진 유형 선택 해제" variant="outline" onPress={()=>change({goal:''},true)}/>:null}<Muted>{data.excluded.some(e=>['closed','cutoff'].includes(e.code))?'다른 날짜·시간을 골라 주세요.':'조건을 바꾸거나 서울 둘러보기에서 장소 정보를 먼저 확인해 주세요.'}</Muted></Card>:null}
    </View>
    {query.cut?<Button title="선택한 컷 해제하고 다시 찾기" variant="outline" onPress={()=>change({cut:''},true)}/>:null}
    <Button title={conditions?'조건 접기':'조건 바꾸기'} variant="outline" expanded={conditions} onPress={()=>setConditions(!conditions)}/>
    {conditions?<Card style={{gap:18}}>
      <Muted>선택하지 않은 항목도 검색을 막지 않아요.</Muted><CalendarField value={date} onChange={next=>change({date:next})}/>
      <View style={{gap:8}}><Title headingLevel={2} size={19}>동행 (선택)</Title><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{PARTIES.map(([value,label])=><Chip key={value} label={label} selected={query.party===value} onPress={()=>change({party:query.party===value?'':value})}/>)}</View></View>
      <View style={{gap:8}}><Title headingLevel={2} size={19}>사진 목적 (선택)</Title><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{GOALS.map(([value,label])=>{const unavailable=data?.goal_counts[value as 'portrait'|'architecture'|'landscape']===0;return <Chip key={value} label={`${label}${unavailable?' (준비 중)':''}`} selected={query.goal===value} disabled={unavailable&&query.goal!==value} onPress={()=>change({goal:query.goal===value?'':value})}/>;})}</View></View>
      <View style={{gap:8}}><Title headingLevel={2} size={19}>방문 시간 (선택 · 한국시간)</Title><View style={{flexDirection:'row',flexWrap:'wrap',gap:8}}>{[['10:00','오전 10시'],['14:00','오후 2시'],['16:00','오후 4시'],['18:00','저녁 6시']].map(([value,label])=><Chip key={value} label={label} selected={query.time===value} onPress={()=>change({time:query.time===value?'':value})}/>)}</View>
        <Field label="방문 시각 직접 입력 (HH:MM, 선택)" value={draftTime} onChange={value=>{setDraftTime(value);setTimeError(false);}} onBlur={commitTime} onSubmit={commitTime} invalid={timeError} describedBy="shot-time-help" keyboard="numeric" placeholder="예: 15:30" autoComplete="off"/>
        <View nativeID="shot-time-help">{timeError?<Body>24시간제로 입력해 주세요. 예: 9:30 또는 1530. 비워 두어도 돼요.</Body>:<Muted>시간 미선택 시 개방시간을 안내해요. 지금 촬영 가능하다는 뜻은 아니에요.</Muted>}</View>
      </View>
    </Card>:null}
    {data?.review_available?<><Button title="검토용 시나리오 보기" expanded={reviewMenu} variant="outline" onPress={()=>setReviewMenu(!reviewMenu)}/>{reviewMenu?<Card style={{gap:8}}><Muted>내일 날짜의 합성 데이터로 확인해요. 실제 장소 안내가 아니에요.</Muted>{CASES.map(([value,label])=><Button key={value} title={`테스트 · ${label}`} variant="outline" onPress={()=>change({date:new Date(Date.parse(today()+'T00:00:00Z')+86400000).toISOString().slice(0,10),review:value,cut:'test-cut-a',time:value==='cutoff'?'16:00':'10:00'},true)}/>)}<Button title="실제 검수 데이터로 돌아가기" variant="outline" onPress={()=>change({review:'',cut:''},true)}/></Card>:null}</>:null}
    <Muted size={13}>화면 조회 결과·공유·길찾기·대체 컷·촬영 완료는 오늘의 한 컷 통계를 추가 허용한 경우에만 집계해요. 완료는 사용자 응답이며 실제 촬영 증명이 아니에요. 정밀 위치·사진·조회 조건은 수집하지 않아요.</Muted>
    <Button title="개인정보 안내 · 통계 선택" variant="outline" onPress={()=>router.push('/privacy')}/>
  </Screen>;
}
