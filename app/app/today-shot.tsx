import React, { useState } from 'react';
import { ActivityIndicator, Linking, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { DEMO, today } from '@/api';
import { track } from '@/analytics';
import { validCalendarDate } from '@/calendar';
import { useAsync, useDocumentTitle } from '@/hooks';
import { Body, Button, Card, Chip, ErrorBox, Field, Muted, Screen, Title } from '@/components/ui';
import { CalendarField } from '@/components/calendar-field';
import { ShotCard } from '@/components/shot-card';
import { fetchShots, shotParams, type Shot, type ShotQuery } from '@/shot-guide';
import { shareText, SHARE_NOTICE } from '@/share';

const first = (v: string | string[] | undefined) => Array.isArray(v) ? v[0] : v ?? '';
const CASES = [['open', '정상 개방'], ['weekly_closed', '정기 휴무'], ['cutoff', '입장마감 전후'], ['temporary_closed', '임시 통제'], ['unknown', '운영정보 미확인'], ['no_alternative', '대체 컷 없음']];

export default function TodayShot() {
  const router = useRouter(), params = useLocalSearchParams();
  const date = validCalendarDate(first(params.date)) ? first(params.date) : today();
  const party = first(params.party), goal = first(params.goal);
  const query: ShotQuery = { date, party: ['solo','pair','family'].includes(party) ? party as ShotQuery['party'] : '',
    goal: ['portrait','architecture','landscape'].includes(goal) ? goal as ShotQuery['goal'] : '',
    time: first(params.time), cut: first(params.cut), review: first(params.review) };
  const validTime = !query.time || /^([01]\d|2[0-3]):[0-5]\d$/.test(query.time);
  const key = shotParams(query).toString();
  const result = useAsync(() => DEMO && validTime ? fetchShots(query) : Promise.resolve(null), [key, validTime]);
  const data = !result.loading && !result.error && validTime ? result.data : null;
  const [notice, setNotice] = useState(''), [reviewMenu, setReviewMenu] = useState(false), [done, setDone] = useState<string[]>([]);
  useDocumentTitle('오늘의 한 컷 · 광화문·정동 · 포토스팟');
  const change = (patch: Record<string, string>) => { setNotice(''); router.setParams(patch); };
  const event = (name: 'shot_directions' | 'shot_alternative' | 'shot_completed', cut: string, outcome: string) => {
    // Synthetic examples must never be counted as successful real visits.
    if (data?.mode !== 'review') void track(name, { cut_id: cut, outcome });
  };
  const navigate = async (shot: Shot) => {
    if (data?.mode === 'review') { setNotice('길찾기 테스트 완료 · 장소 중심점 대신 이 컷의 촬영 핀을 목적지로 사용해요. 실제 지도는 열지 않았어요.'); return; }
    try { await Linking.openURL(shot.navigation_url); event('shot_directions', shot.cut_id, 'opened'); }
    catch { setNotice('지도를 열지 못했어요. 잠시 후 다시 시도해 주세요.'); }
  };
  const share = async (shot: Shot) => {
    const origin = typeof window !== 'undefined' ? window.location.origin : 'https://photospot.litaandd.com';
    const url = `${origin}/today-shot?${shotParams({ ...query, cut: shot.cut_id })}`;
    setNotice(SHARE_NOTICE[await shareText({ title: `${shot.title} · 오늘의 한 컷`, lines: [data?.mode === 'review' ? '기능 검수용 합성 예시 · 현장 안내 아님' : shot.place_name, query.date], url })] ?? '');
  };
  return <Screen style={{ gap: 18 }}>
    <Button title="서울 둘러보기로" variant="outline" onPress={() => router.push({ pathname: '/browse', params: { city: 'seoul', date } })}/>
    <View style={{ gap: 7 }}><Muted>광화문 · 정동</Muted><Title headingLevel={1} size={32}>오늘의 한 컷</Title><Body>어디에 서고, 어디를 보고, 어떻게 담을지.</Body><Muted>로그인과 프로필 없이 이용해요. 아래 선택은 모두 비워 두어도 괜찮아요.</Muted></View>
    {query.review ? <Card><Body headingLevel={2}>검토용 합성 예시 · 현장 안내 아님</Body><Muted>좌표·시간표·검증 표시는 기능 테스트 값이에요. 실제 촬영 가능 여부나 장소 안내로 사용하지 마세요.</Muted></Card> : null}
    <CalendarField value={date} onChange={next => change({ date: next })}/>
    {date < today() ? <Card><Body>공유된 날짜가 지났어요. 원래 날짜를 유지하고 있으며 현재 촬영 가능 여부는 안내하지 않아요.</Body><Button title="오늘 날짜로 변경" onPress={() => change({date:today()})}/></Card> : null}
    <View style={{ gap: 8 }}><Body headingLevel={2}>누구와 가나요? <Muted>(선택)</Muted></Body><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{[['solo','혼자'],['pair','둘이'],['family','가족']].map(([value,label]) => <Chip key={value} label={label} selected={query.party===value} onPress={() => change({party: query.party===value ? '' : value})}/>)}</View></View>
    <View style={{ gap: 8 }}><Body headingLevel={2}>어떤 사진을 원하나요? <Muted>(선택)</Muted></Body><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{[['portrait','인물'],['architecture','건축'],['landscape','풍경']].map(([value,label]) => <Chip key={value} label={label} selected={query.goal===value} onPress={() => change({goal: query.goal===value ? '' : value})}/>)}</View></View>
    <View style={{ gap: 8 }}><Body headingLevel={2}>방문 시간 <Muted>(선택 · 한국시간)</Muted></Body><View style={{ flexDirection: 'row', flexWrap: 'wrap', gap: 8 }}>{[['10:00','오전 10시'],['14:00','오후 2시'],['16:00','오후 4시'],['18:00','저녁 6시']].map(([value,label]) => <Chip key={value} label={label} selected={query.time===value} onPress={() => change({time: query.time===value ? '' : value})}/>)}</View><Field label="방문 시각 직접 입력 (HH:MM, 선택)" value={query.time} onChange={value => change({time:value})}/>{!validTime ? <Body>24시간제로 입력해 주세요. 예: 15:30. 비워 두어도 돼요.</Body> : <Muted>시간 미선택 시 개방시간을 안내하며, 지금 촬영 가능하다고 판단하지 않아요.</Muted>}</View>
    {!DEMO ? <Muted>이 기능은 포토스팟 공개 웹에서 준비 중이에요.</Muted> : null}
    {result.loading ? <View accessibilityRole="progressbar" accessibilityLabel="촬영 조건 확인 중"><ActivityIndicator/><Muted>선택한 날짜와 이용 조건을 확인하고 있어요.</Muted></View> : null}
    {result.error ? <ErrorBox message={result.error instanceof Error ? result.error.message : '촬영 안내 확인에 실패했어요.'} onRetry={result.reload}/> : null}
    {query.cut ? <Button title="선택한 컷 해제하고 다시 찾기" variant="outline" onPress={() => change({ cut:'' })}/> : null}
    {data?.replacement_reason ? <Card><Body>선택한 컷을 이용할 수 없어요</Body><Muted>{data.replacement_reason}</Muted>{data.alternative ? <><Body>같은 사진 목적의 대체 컷 · {data.alternative.place_name}</Body><Muted>{data.alternative.title}</Muted><Button title="대체 컷 열기" onPress={() => { event('shot_alternative', data.alternative!.cut_id, 'opened'); change({cut:data.alternative!.cut_id}); }}/></> : null}</Card> : null}
    {data?.primary ? <><Body headingLevel={2}>추천 한 컷 · {date}{query.time ? ` ${query.time}` : ''}</Body><ShotCard shot={data.primary} review={data.mode==='review'} completed={done.includes(`${data.primary.cut_id}/${date}`)} onNavigate={() => void navigate(data.primary!)} onShare={() => void share(data.primary!)} onComplete={() => { const shot=data.primary!; setDone(v => [...v,`${shot.cut_id}/${date}`]); event('shot_completed',shot.cut_id,'reported'); setNotice(data.mode==='review' ? '테스트 완료 · 실제 촬영 집계에는 포함하지 않았어요.' : '고마워요. 사진이나 위치는 수집하지 않아요.'); }}/></> : null}
    {data?.empty_message ? <Card><Body headingLevel={2}>{data.empty_message}</Body><Muted>{data.mode==='catalog' ? `현재 ${data.candidate_count}개 후보의 촬영 핀과 이용 조건을 확인 중이에요.` : '확인된 대안도 없어 안내를 중단했어요.'}</Muted><Muted>날짜·시간을 바꾸거나 서울 둘러보기에서 장소 정보를 먼저 확인해 주세요.</Muted></Card> : null}
    {notice ? <View accessibilityLiveRegion="polite"><Body>{notice}</Body></View> : null}
    {data?.review_available ? <><Button title="검토용 시나리오 보기" variant="outline" onPress={() => setReviewMenu(!reviewMenu)}/>{reviewMenu ? <Card><Muted>합성 데이터로 기능을 확인해요. 실제 장소 추천과 분리돼 있어요.</Muted>{CASES.map(([value,label]) => <Button key={value} title={`테스트 · ${label}`} variant="outline" onPress={() => change({review:value,cut:'test-cut-a',time:value==='cutoff' ? '16:00' : '10:00'})}/>)}<Button title="실제 검수 데이터로 돌아가기" variant="outline" onPress={() => change({review:'',cut:''})}/></Card> : null}</> : null}
    <Muted size={12}>길찾기·대체 컷·촬영 완료 버튼은 기존 통계 선택에 동의한 경우에만 집계해요. 완료는 사용자 응답이며 실제 촬영의 증명은 아니에요. 정밀 위치·사용자 사진은 받지 않아요.</Muted>
    <Button title="개인정보 안내 · 통계 선택" variant="outline" onPress={() => router.push('/privacy')}/>
  </Screen>;
}
