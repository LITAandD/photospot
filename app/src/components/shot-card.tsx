import React, { useEffect, useState } from 'react';
import { Image, Linking, Platform, Text, View } from 'react-native';
import Svg, { Rect, Path, Circle, Line, G, Text as SvgText } from 'react-native-svg';
import { Body, Button, Card, Muted, Title } from './ui';
import { bearingLabel, type Hours, type Shot, type Source } from '@/shot-guide';
import { colors, fonts } from '@/theme';

const clock = (value: string) => value.slice(0, 5);
const hours = (rows: Hours[]) => rows.map(r => r.all_day ? '24시간' : `${clock(r.opens)}–${clock(r.closes)}${r.last_entry ? ` · 입장마감 ${clock(r.last_entry)}` : ' · 별도 입장마감 없음'}`).join(' / ');
const sourceNames: Record<Source['kinds'][number], string> = {place_hours:'장소 운영시간',cut_access:'컷 접근',photography:'촬영 허용',pin:'촬영 핀',light:'빛 관찰'};
const Step = ({children}: {children: React.ReactNode}) => <Text accessibilityRole="header" aria-level={3} style={{fontFamily:fonts.semibold,fontWeight:'600',fontSize:17,color:colors.ink}}>{children}</Text>;

/** Explicit reviewed composition data, not a place map or a generated photograph. */
export function ShotDiagram({ shot }: { shot: Shot }) {
  const composition = shot.visual.composition;
  if (!composition) return <Muted>검수된 구도 도식이 없어요.</Muted>;
  const portrait = composition.orientation === 'portrait', width = portrait ? 210 : 320;
  const x = 24 + (width-48) * composition.subject_x;
  return <View accessibilityRole="image" accessibilityLabel={`구도 도식, 실제 사진·지도 아님. ${shot.framing}. ${bearingLabel(shot.pin.bearing_deg)}`} style={{ backgroundColor: colors.accentSoft, borderRadius: 18, overflow: 'hidden' }}>
    <Svg width="100%" height={portrait ? 300 : 230} viewBox={`0 0 ${width} 230`}>
      <Rect x={24} y={18} width={width-48} height={180} rx={14} fill="none" stroke={colors.accentInk} strokeWidth={1.5} />
      {[1,2].map(i => <Line key={i} x1={24+(width-48)*i/3} y1={18} x2={24+(width-48)*i/3} y2={198} stroke={colors.accentInk} strokeDasharray="3 7" opacity={0.25}/>)}
      {composition.subject === 'portrait' ? <G testID="diagram-portrait" stroke={colors.accentInk} strokeWidth={3} fill="none"><Circle cx={x} cy={82} r={12}/><Path d={`M${x} 94 v42 m-24 -30 l24 10 l24 -10 M${x} 136 l-18 20 M${x} 136 l18 20`}/></G>
      : composition.subject === 'architecture' ? <G testID="diagram-architecture" transform={`translate(${x-80},0)`}><Path d="M30 126 V78 L80 54 L130 78 V126 Z M30 78 H130 M46 85 V126 M70 85 V126 M94 85 V126 M118 85 V126" fill="none" stroke={colors.accentInk} strokeWidth={3}/></G>
      : <G testID="diagram-landscape"><Path d={`M26 112 H${width-26} M26 111 L${width/3} 70 L${width/2} 110 L${width*0.7} 85 L${width-26} 112`} fill="none" stroke={colors.accentInk} strokeWidth={3}/></G>}
      <G transform={`rotate(${-shot.pin.bearing_deg},43,40)`}><Path d="M43 50 V30 L38 38 M43 30 L48 38" stroke={colors.accentInk} strokeWidth={2}/><SvgText x={43} y={24} textAnchor="middle" fontSize={10}>N</SvgText></G>
      <Path d={`M${width/2} 174 V151 m-6 8 l6 -8 l6 8`} stroke={colors.accentInk} strokeWidth={2} fill="none"/>
      <Circle cx={width/2} cy={185} r={10} fill={colors.terracotta}/>
      <SvgText x={width/2} y={219} textAnchor="middle" fontSize={10} fill={colors.ink}>촬영자 위치 · 실제 사진·지도 아님</SvgText>
    </Svg>
  </View>;
}

export function ShotCard({ shot, review, onNavigate, onShare, onComplete, completed }: {
  shot: Shot; review: boolean; onNavigate: (provider:'kakao'|'naver'|'google') => void; onShare: () => void; onComplete: () => void; completed: boolean;
}) {
  const [sources, setSources] = useState(false), [linkError, setLinkError] = useState(false);
  const [mobile,setMobile] = useState(Platform.OS !== 'web');
  const [ratio,setRatio] = useState(shot.visual.width && shot.visual.height ? shot.visual.width/shot.visual.height : 1.5);
  useEffect(() => { if (Platform.OS === 'web') setMobile(/Android|iPhone|iPad|iPod/i.test(navigator.userAgent)); },[]);
  const open = (url: string) => { setLinkError(false); Linking.openURL(url).catch(() => setLinkError(true)); };
  return <Card style={{ gap: 14 }} testID="shot-card">
    <View style={{ gap: 5 }}><Muted>{shot.place_name}</Muted><Title headingLevel={2} size={24}>{shot.title}</Title><Body>{shot.reason}</Body></View>
    <View style={{gap:8}}><Button title="카카오맵으로 길찾기" onPress={() => onNavigate('kakao')}/><Button title="이 컷 공유하기" variant="outline" onPress={onShare}/></View>
    {mobile ? <><Button title="네이버 지도 앱으로 길찾기" variant="outline" onPress={() => onNavigate('naver')}/><Muted size={13}>앱이 열리지 않으면 위 카카오맵 웹 길찾기를 이용해 주세요.</Muted></> : null}
    {!review ? <Text accessibilityRole="link" onPress={() => onNavigate('google')} style={{color:colors.accentInk,minHeight:44,paddingVertical:12}}>Google 지도에서 촬영 위치 보기</Text> : null}
    {review ? <Muted size={13}>합성 테스트: 실제 지도나 장소로 안내하지 않아요.</Muted> : <Muted size={13}>목적지는 촬영 핀이에요. 마지막 구간은 아래 진입 안내와 현장 통제를 확인하세요.</Muted>}
    {shot.visual.kind === 'photo' && shot.visual.image_url ? <Image source={{ uri: shot.visual.image_url }} resizeMode="contain" onLoad={e => {const {width,height}=e.nativeEvent.source; if(width && height)setRatio(width/height);}} style={{ width: '100%', aspectRatio: ratio, maxHeight: 440 }} accessibilityLabel={`${shot.title} 실촬영 예시`} /> : <ShotDiagram shot={shot} />}
    <Muted size={13}>{shot.visual.creator} · {shot.visual.rights}</Muted>
    {shot.visual.source_url ? <Button title="사진 출처" variant="outline" onPress={() => open(shot.visual.source_url!)} /> : null}
    {shot.visual.license_url ? <Button title="사진 이용 조건" variant="outline" onPress={() => open(shot.visual.license_url!)} /> : null}
    <View style={{ gap: 6 }}><Step>01 · 여기에 서세요</Step><Body>{shot.pin.standing_landmark}</Body><Muted>촬영 핀 {shot.pin.lat}, {shot.pin.lng}{review ? ' · 합성 테스트 좌표' : ' · 장소 입구와 다를 수 있어요'}</Muted><Muted>{shot.pin.entry_instructions}</Muted></View>
    <View style={{ gap: 6 }}><Step>02 · 이쪽을 바라보세요</Step><Body>{shot.pin.look_toward}</Body><Muted>{bearingLabel(shot.pin.bearing_deg)} · 진북 기준. 눈앞의 기준물도 함께 확인하세요.</Muted></View>
    <View style={{ gap: 6 }}><Step>03 · 휴대폰은 이렇게</Step><Body>{shot.framing}</Body>{shot.light_note ? <Muted>현장 빛 관찰 · {shot.light_note}</Muted> : <Muted>좋은 빛이 드는 시간은 아직 확인하지 않았어요.</Muted>}</View>
    <View style={{ backgroundColor: colors.bg, borderRadius: 12, padding: 12, gap: 8 }}>
      <Step>가기 전에 확인</Step><Body>{shot.availability_note}</Body>
      {shot.place_hours.length ? <Muted>장소 운영 · {hours(shot.place_hours)}</Muted> : null}<Muted>{shot.place_hours_note}</Muted>
      <Muted>이 컷의 접근 · {hours(shot.cut_hours)}</Muted><Muted>{shot.cut_hours_note}</Muted><Body>촬영 제한 · {shot.restrictions}</Body>
    </View>
    <Button title={sources ? '출처·확인일 접기' : '정보 출처·확인일 보기'} expanded={sources} variant="outline" onPress={() => setSources(!sources)} />
    {sources ? <View style={{ gap: 8 }}><Muted>현장 재현 확인 · {shot.field_checked_at}{review ? ' (테스트 값)' : ''}</Muted>{shot.sources.map((s,i) => <View key={i}><Muted>{s.kinds.map(k => sourceNames[k]).join('·')} 근거 · {s.label} · {s.checked_at} 확인 · {s.valid_until}까지 재확인 대상</Muted>{!review ? <Button title={`${s.kinds.map(k=>sourceNames[k]).join('·')} 출처 열기`} variant="outline" onPress={() => open(s.url)} /> : null}</View>)}</View> : null}
    <Button title={completed ? '확인했어요 · 감사합니다' : '안내대로 찍었어요'} variant="outline" disabled={completed} onPress={onComplete}/>
    {linkError ? <Body>링크를 열지 못했어요. 잠시 후 다시 시도해 주세요.</Body> : null}
  </Card>;
}
