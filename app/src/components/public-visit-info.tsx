import React, { useState } from 'react';
import { Pressable, Text, View } from 'react-native';
import type { PublicPlace } from '@/public-browse';
import { admissionLead, visitHours } from '@/public-visit';
import { colors, fonts } from '@/theme';
import { Body, Card, Muted } from './ui';

export function PublicVisitInfo({ place, date, openSource }: { place: PublicPlace; date: string; openSource: (url: string) => void }) {
  const [expanded, setExpanded] = useState(false);
  const { hours } = place, view = visitHours(hours);
  const fees = place.facts.filter(fact => fact.kind === 'admission');
  return <Card testID="public-visit-info" style={{ padding: 14, gap: 4, borderRadius: 18, backgroundColor: colors.accentSoft }}>
    <Body size={16} headingLevel={2}>촬영일 기준 방문 정보</Body>
    <Text style={{ color: colors.accentInk, fontFamily: fonts.medium, fontSize: 14 }}>선택한 날짜 · {date}</Text>
    <View style={{ flexDirection: 'row', alignItems: 'baseline', gap: 10, flexWrap: 'wrap' }}>
      <Text style={{ color: view.status === 'closed' ? colors.terracotta : colors.ink, fontFamily: fonts.semibold, fontSize: view.status === 'hours' ? 24 : 19, lineHeight: 34 }}>{view.title}</Text>
      {view.cutoff ? <Body size={13}>입장 마감 {view.cutoff}</Body> : null}
    </View>
    {hours?.stale ? <Muted size={12}>재확인 필요 · 공식 안내를 확인해 주세요.</Muted> : null}
    <View style={{ borderTopWidth: 1, borderTopColor: colors.line, marginTop: 3, paddingTop: 7, gap: 3 }}>
      {fees.length ? fees.map((fact, index) => <Body key={index} size={14}>{fact.label} · {admissionLead(fact.value)}</Body>) : <Body size={14}>관람료 · 확인 필요</Body>}
    </View>
    <Pressable accessibilityRole="button" aria-expanded={expanded} accessibilityState={{ expanded }} onPress={() => setExpanded(!expanded)} style={{ minHeight: 44, justifyContent: 'center' }}>
      <Text style={{ fontFamily: fonts.medium, fontSize: 12, color: colors.accentInk }}>{expanded ? '방문 정보 접기 −' : '요금 조건·출처·확인일 ＋'}</Text>
    </Pressable>
    {expanded ? <View style={{ gap: 6 }}>
      {hours ? <>
        <Muted size={12}>{hours.summary}</Muted>
        {hours.notes.map((note, index) => <Muted size={12} key={index}>{note}</Muted>)}
        <Pressable accessibilityRole="link" onPress={() => openSource(hours.source_url)} style={{ minHeight: 44, justifyContent: 'center' }}><Muted size={12}>{hours.source_label} · {hours.checked_at} {hours.provider === 'openstreetmap' ? '수집' : '확인'} ↗</Muted></Pressable>
      </> : <Muted size={12}>확인된 시간표가 없어요. 방문 전 공식 안내나 지도를 확인해 주세요.</Muted>}
      {fees.map((fact, index) => <View key={index} style={{ gap: 4 }}><Body size={13}>{fact.value}</Body><Pressable accessibilityRole="link" onPress={() => openSource(fact.source_url)} style={{ minHeight: 44, justifyContent: 'center' }}><Muted size={12}>{fact.source_label} · {fact.checked_at} 확인 ↗</Muted></Pressable></View>)}
      <Muted size={12}>등록된 안내이며 임시 휴무·특별 개방에 따라 달라질 수 있어요. 할인·면제 대상과 특별 관람 요금은 공식 안내를 확인해 주세요.</Muted>
    </View> : null}
  </Card>;
}
