import React, { useState } from 'react';
import { Image, Linking, View } from 'react-native';
import Svg, { Rect, Path, Circle, Line, Text as SvgText } from 'react-native-svg';
import { Body, Button, Card, Muted, Title } from './ui';
import type { Hours, Shot } from '@/shot-guide';
import { colors } from '@/theme';

const clock = (value: string) => value.slice(0, 5);
const hours = (rows: Hours[]) => rows.map(r => r.all_day ? '24시간' : `${clock(r.opens)}–${clock(r.closes)}${r.last_entry ? ` · 입장마감 ${clock(r.last_entry)}` : ' · 별도 입장마감 없음'}`).join(' / ');

/** Original composition diagram, deliberately not a map or simulated photograph. */
export function ShotDiagram({ shot }: { shot: Shot }) {
  return <View accessibilityRole="image" accessibilityLabel={`구도 도식, 실제 사진·지도 아님. ${shot.framing}. 촬영자는 아래 핀, 바라볼 기준물은 위쪽.`} style={{ backgroundColor: colors.accentSoft, borderRadius: 18, overflow: 'hidden' }}>
    <Svg width="100%" height={230} viewBox="0 0 320 230">
      <Rect x={24} y={18} width={272} height={180} rx={14} fill="none" stroke={colors.accentInk} strokeWidth={1.5} />
      <Line x1={115} y1={18} x2={115} y2={198} stroke={colors.accentInk} strokeDasharray="3 7" opacity={0.25}/>
      <Line x1={205} y1={18} x2={205} y2={198} stroke={colors.accentInk} strokeDasharray="3 7" opacity={0.25}/>
      <Path d="M92 112 L92 75 L160 50 L228 75 L228 112 Z M105 75 L215 75 M116 82 L116 112 M144 82 L144 112 M176 82 L176 112 M204 82 L204 112" fill="none" stroke={colors.accentInk} strokeWidth={3}/>
      <Path d="M160 165 L160 132 M153 140 L160 132 L167 140" stroke={colors.accentInk} strokeWidth={3} fill="none"/>
      <Circle cx={160} cy={182} r={13} fill={colors.terracotta}/><Circle cx={160} cy={182} r={4} fill="white"/>
      <SvgText x={160} y={37} textAnchor="middle" fontSize={12} fill={colors.accentInk}>바라볼 기준물</SvgText>
      <SvgText x={160} y={219} textAnchor="middle" fontSize={12} fill={colors.ink}>촬영자 위치 · 구도 도식 (실제 사진·지도 아님)</SvgText>
    </Svg>
  </View>;
}

export function ShotCard({ shot, review, onNavigate, onShare, onComplete, completed }: {
  shot: Shot; review: boolean; onNavigate: () => void; onShare: () => void; onComplete: () => void; completed: boolean;
}) {
  const [sources, setSources] = useState(false), [linkError, setLinkError] = useState(false);
  const open = (url: string) => { setLinkError(false); Linking.openURL(url).catch(() => setLinkError(true)); };
  return <Card style={{ gap: 16 }} testID="shot-card">
    <View style={{ gap: 5 }}><Muted>{shot.place_name}</Muted><Title headingLevel={2} size={24}>{shot.title}</Title><Body>{shot.reason}</Body></View>
    {shot.visual.kind === 'photo' && shot.visual.image_url ? <Image source={{ uri: shot.visual.image_url }} resizeMode="contain" style={{ width: '100%', height: 230 }} accessibilityLabel={`${shot.title} 실촬영 예시`} /> : <ShotDiagram shot={shot} />}
    <Muted size={12}>{shot.visual.creator} · {shot.visual.rights}</Muted>
    {shot.visual.source_url ? <Button title="사진 출처" variant="outline" onPress={() => open(shot.visual.source_url!)} /> : null}
    {shot.visual.license_url ? <Button title="사진 이용 조건" variant="outline" onPress={() => open(shot.visual.license_url!)} /> : null}
    <View style={{ gap: 6 }}><Body headingLevel={3}>01 · 여기에 서세요</Body><Body>{shot.pin.standing_landmark}</Body><Muted>촬영 핀 {shot.pin.lat}, {shot.pin.lng}{review ? ' · 합성 테스트 좌표' : ' · 장소 입구와 다를 수 있어요'}</Muted><Muted>{shot.pin.entry_instructions}</Muted></View>
    <View style={{ gap: 6 }}><Body headingLevel={3}>02 · 이쪽을 바라보세요</Body><Body>{shot.pin.look_toward}</Body><Muted>진북 기준 {shot.pin.bearing_deg}° · 방향 숫자보다 눈앞의 기준물을 함께 확인하세요.</Muted></View>
    <View style={{ gap: 6 }}><Body headingLevel={3}>03 · 휴대폰은 이렇게</Body><Body>{shot.framing}</Body>{shot.light_note ? <Muted>현장 빛 관찰 · {shot.light_note}</Muted> : <Muted>좋은 빛이 드는 시간은 아직 확인하지 않았어요.</Muted>}</View>
    <View style={{ backgroundColor: colors.bg, borderRadius: 12, padding: 12, gap: 8 }}>
      <Body headingLevel={3}>가기 전에 확인</Body><Body>{shot.availability_note}</Body>
      <Muted>장소 운영 · {hours(shot.place_hours)}</Muted><Muted>{shot.place_hours_note}</Muted>
      <Muted>이 컷의 접근 · {hours(shot.cut_hours)}</Muted><Muted>{shot.cut_hours_note}</Muted>
      <Body>촬영 제한 · {shot.restrictions}</Body>
    </View>
    <Button title={sources ? '출처·확인일 접기' : '정보 출처·확인일 보기'} variant="outline" onPress={() => setSources(!sources)} />
    {sources ? <View style={{ gap: 8 }}><Muted>현장 재현 확인 · {shot.field_checked_at}{review ? ' (테스트 값)' : ''}</Muted>{shot.sources.map((s, i) => <View key={i}><Muted>{s.label} · {s.checked_at} 확인 · {s.valid_until}까지 재확인 대상</Muted>{!review ? <Button title={`출처 ${i + 1} 열기`} variant="outline" onPress={() => open(s.url)} /> : null}</View>)}</View> : null}
    <Button title="촬영 위치로 길찾기" onPress={onNavigate} />
    {review ? <Muted size={12}>검토 모드: 실제 장소로 안내하지 않고 핀 연결만 시뮬레이션해요.</Muted> : <Muted size={12}>지도가 마지막 구간을 다르게 안내하면 위 진입 안내를 따르세요. 통제 구역에는 들어가지 마세요.</Muted>}
    <Button title="이 컷 공유하기" variant="outline" onPress={onShare}/>
    <Button title={completed ? '확인했어요 · 감사합니다' : '안내대로 찍었어요'} variant="outline" disabled={completed} onPress={onComplete}/>
    {linkError ? <Body>링크를 열지 못했어요. 잠시 후 다시 시도해 주세요.</Body> : null}
  </Card>;
}
