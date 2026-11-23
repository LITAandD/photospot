import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Platform, Pressable, Text, useWindowDimensions, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { naverMapUrl } from '@photospot/client';
import { formatVisitDate } from "@/format-date";
import { DEMO, today } from '@/api';
import { track } from '@/analytics';
import { browseContext, browseHref } from '@/browse-context';
import { BrowseError, fetchBrowse, type PublicPlace } from '@/public-browse';
import { errorMessage, useAsync, useNoIndex, useDocumentTitle } from '@/hooks';
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { PlacePhoto, PhotoCredit } from '@/components/place-photo';
import { PlaceHours } from '@/components/place-hours';
import { BrowseCustomize } from '@/components/browse-customization';
import { shareText, shareUrl, SHARE_NOTICE } from '@/share';
import { VisitorExamples } from '@/components/visitor-examples';
import { PublicVisitInfo } from '@/components/public-visit-info';
import { colors, fonts } from '@/theme';

export default function PublicPlacePage() {
  const router = useRouter(), params = useLocalSearchParams();
  const { width } = useWindowDimensions();
  const mobile = Platform.OS === 'web' && width < 680;
  const context = browseContext({ ...params, place: params.id }, today());
  const request = typeof params.request === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(params.request) ? params.request : null;
  const [error, setError] = useState<string | null>(null), [sources, setSources] = useState(false);
  const [shareNotice, setShareNotice] = useState<string | null>(null);
  const [details, setDetails] = useState(false);
  const result = useAsync(() => context?.place && DEMO ? fetchBrowse<PublicPlace>(context, true) : Promise.resolve(null), [context?.city, context?.date, context?.place]);
  const place = result.data;
  const missing = !context?.place || result.error instanceof BrowseError && [404, 422].includes(result.error.status);
  useDocumentTitle(missing ? '장소를 찾을 수 없어요 · 포토스팟' : place ? `${place.name} · ${place.browse_origin.label} · 포토스팟` : '장소 정보 · 포토스팟');
  useNoIndex(missing, '장소를 찾을 수 없어요 · 포토스팟');
  useEffect(() => { if (place) void track('place_view', { place_id: place.place_id, surface: 'browse', request_id: request }); }, [!!place, place?.place_id, request]);
  const back = () => router.dismissTo(context ? browseHref(context, false) : '/browse');
  const openSource = (url: string) => { setError(null); void Linking.openURL(url).catch(() => setError('출처를 열지 못했어요. 다시 시도해 주세요.')); };
  const actions = place && context ? <View testID="public-place-actions" style={{ gap: 6, paddingHorizontal: mobile ? 16 : 0, paddingVertical: mobile ? 8 : 0, backgroundColor: mobile ? colors.card : undefined, borderTopWidth: mobile ? 1 : 0, borderTopColor: colors.line }}>
    {shareNotice ? <View role="status" aria-live="polite" accessibilityLiveRegion="polite"><Muted size={12}>{shareNotice}</Muted></View> : null}
    {error ? <View accessibilityRole="alert"><Body size={13}>{error}</Body></View> : null}
    <View style={{ flexDirection: 'row', gap: 10 }}>
      <View style={{ flex: 1 }}><Button title="공유" accessibilityLabel="이 장소 공유하기" variant="outline" onPress={async () => {
        const url = shareUrl(`/browse/${encodeURIComponent(place.place_id)}`, 'share', { city: context.city, date: context.date });
        setShareNotice(SHARE_NOTICE[await shareText({ title: place.name, lines: [place.name, context.date], url })]);
      }} /></View>
      <View style={{ flex: 1 }}><Button title="지도 열기" accessibilityLabel="네이버 지도 열기" onPress={() => { setError(null); const url = naverMapUrl(place.name); if (url) void Linking.openURL(url).then(() => { void track('map_open', { place_id: place.place_id, surface: 'browse', request_id: request }); }).catch(() => setError('지도를 열지 못했어요.')); }} /></View>
    </View>
  </View> : null;
  const background = place?.facts.filter(fact => ['photo_point', 'background', 'setting', 'recommended_time'].includes(fact.kind)) ?? [];
  return <Screen style={{ gap: 12, paddingHorizontal: mobile ? 21 : 22 }} footer={mobile ? actions : null}>
    <Pressable accessibilityRole="button" accessibilityLabel="둘러보기 목록으로 돌아가기" onPress={back} style={{ minHeight: 44, paddingHorizontal: 16, borderRadius: 16, borderWidth: 1, borderColor: colors.line, backgroundColor: colors.card, justifyContent: 'center' }}><Text style={{ fontFamily: fonts.medium, fontSize: 14, color: colors.ink }}>‹ 둘러보기</Text></Pressable>
    {missing ? <Card><Body>이 장소를 찾을 수 없어요.</Body><Muted>선택한 도시의 목록에서 다른 장소를 골라 주세요.</Muted></Card> : <>
      {result.loading ? <View accessibilityLiveRegion="polite"><ActivityIndicator /><Muted>방문 정보를 불러오고 있어요.</Muted></View> : null}
      {result.error ? <ErrorBox message={errorMessage(result.error)} onRetry={result.reload} /> : null}
    </>}
    {place && context ? <>
      <View style={{ gap: 3 }}><Title headingLevel={1} size={31}>{place.name}</Title>
        {place.address ? <Muted size={14}>{place.address}</Muted> : null}</View>
      {place.cover_photo ? <View style={{ gap: 3 }}><PlacePhoto photo={place.cover_photo} naturalRatio={Platform.OS === 'web'} fit="contain" style={{ width: '100%', minHeight: 60, borderRadius: 14, ...(Platform.OS !== 'web' ? { aspectRatio: 1 } : {}) }} label={place.name} />
        <PhotoCredit photo={place.cover_photo} compact /></View> : <Muted>사진 준비 중</Muted>}
      <PublicVisitInfo key={`${place.place_id}:${context.date}`} place={place} date={context.date} openSource={openSource} />
      {background.length ? <Card style={{ gap: 10, borderRadius: 18 }}>
        <Body headingLevel={2} size={18}>어디에서 찍을까요?</Body>
        {background.map((fact, index) => <View key={index} style={{ gap: 3 }}><Muted size={12}>{fact.label}</Muted><Body size={14}>{fact.value}</Body>
          {fact.kind === 'photo_point' && fact.source_label.includes('관람코스') ? <Pressable accessibilityRole="link" style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => openSource(fact.source_url)}><Text style={{ fontFamily: fonts.medium, fontSize: 13, color: colors.accentInk }}>공식 관람코스 보기 ↗</Text></Pressable> : null}
        </View>)}
        <Pressable accessibilityRole="button" accessibilityState={{ expanded: sources }} aria-expanded={sources} style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => setSources(!sources)}><Body size={13}>{sources ? '정보 출처 접기 −' : '정보 출처·확인일 보기 ＋'}</Body></Pressable>
        {sources ? background.map((fact, index) => <Pressable key={index} accessibilityRole="link" style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => openSource(fact.source_url)}><Muted size={12}>{fact.label} · {fact.source_label} · {fact.checked_at} 확인 ↗</Muted></Pressable>) : null}
      </Card> : null}
      {!mobile ? actions : null}
      <Muted size={12}>{formatVisitDate(context.date)} · {place.browse_origin.label} 기준 {(place.distance_m / 1000).toFixed(1)}km (직선거리)</Muted>
      <Card style={{ gap: 8, paddingVertical: 10, borderRadius: 18 }}>
        <Pressable accessibilityRole="button" accessibilityLabel="상세 방문 안내" aria-expanded={details} accessibilityState={{ expanded: details }} style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => setDetails(!details)}><Body headingLevel={2}>방문 전 확인 {details ? '−' : '＋'}</Body></Pressable>
        <Muted size={12}>전체 시간표·휴관일·예약 안내</Muted>
        {details ? <>
          <PlaceHours key={`${place.place_id}:${context.date}`} place={{ name: place.name, hours: place.hours, place_group: place.place_group }} />
          {place.facts.filter(fact => fact.kind === 'reservation').map((fact, index) => <View key={index} style={{ gap: 4 }}><Body size={14}>{fact.label}</Body><Muted>{fact.value}</Muted><Pressable accessibilityRole="link" style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => openSource(fact.source_url)}><Muted size={12}>{fact.source_label} · {fact.checked_at} 확인 ↗</Muted></Pressable></View>)}
        </> : null}
      </Card>
      <VisitorExamples placeId={place.place_id} placeName={place.name} />
      <Card style={{ gap: 12 }}><Body headingLevel={2}>내 취향과 맞는지도 알아볼까요?</Body><Muted size={12}>위의 장소 정보는 맞춤 설정 없이 볼 수 있어요. 체형·색조·성향 정합도는 원하는 정보를 입력한 뒤 확인할 수 있어요.</Muted><BrowseCustomize context={context} /></Card>
    </> : null}
  </Screen>;
}
