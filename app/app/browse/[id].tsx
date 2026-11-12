import React, { useEffect, useState } from 'react';
import { ActivityIndicator, Linking, Pressable, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import { naverMapUrl } from '@photospot/client';
import { DEMO, today } from '@/api';
import { track } from '@/analytics';
import { browseContext, browseHref } from '@/browse-context';
import { BrowseError, fetchBrowse, type PublicPlace } from '@/public-browse';
import { errorMessage, useAsync, useNoIndex } from '@/hooks';
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { PlacePhoto, PhotoCredit } from '@/components/place-photo';
import { PlaceHours } from '@/components/place-hours';
import { BrowseCustomize } from '@/components/browse-customization';

export default function PublicPlacePage() {
  const router = useRouter(), params = useLocalSearchParams();
  const context = browseContext({ ...params, place: params.id }, today());
  const request = typeof params.request === 'string' && /^[a-zA-Z0-9_-]{1,64}$/.test(params.request) ? params.request : null;
  const [error, setError] = useState<string | null>(null), [sources, setSources] = useState(false);
  const result = useAsync(() => context?.place && DEMO ? fetchBrowse<PublicPlace>(context, true) : Promise.resolve(null), [context?.city, context?.date, context?.place]);
  const place = result.data;
  const missing = !context?.place || result.error instanceof BrowseError && [404, 422].includes(result.error.status);
  useNoIndex(missing, '장소를 찾을 수 없어요 · 포토스팟');
  useEffect(() => { if (place) void track('place_view', { place_id: place.place_id, surface: 'browse', request_id: request }); }, [!!place, place?.place_id, request]);
  const back = () => router.dismissTo(context ? browseHref(context, false) : '/browse');
  const openSource = (url: string) => { setError(null); void Linking.openURL(url).catch(() => setError('출처를 열지 못했어요. 다시 시도해 주세요.')); };
  return <Screen>
    <Button title="둘러보기 목록으로 돌아가기" variant="outline" onPress={back} />
    {missing ? <Card><Body>이 장소를 찾을 수 없어요.</Body><Muted>선택한 도시의 목록에서 다른 장소를 골라 주세요.</Muted></Card> : <>
      {result.loading ? <View accessibilityLiveRegion="polite"><ActivityIndicator /><Muted>방문 정보를 불러오고 있어요.</Muted></View> : null}
      {result.error ? <ErrorBox message={errorMessage(result.error)} onRetry={result.reload} /> : null}
    </>}
    {place && context ? <>
      <Title>{place.name}</Title>
      <Muted size={12}>{context.date} · {place.browse_origin.label} 기준 {(place.distance_m / 1000).toFixed(1)}km (직선거리)</Muted>
      <PlacePhoto photo={place.cover_photo} placeholder="공간 사진 수집 중" fit="contain" style={{ width: '100%', aspectRatio: 1 }} label={place.name} />
      {place.cover_photo ? <PhotoCredit photo={place.cover_photo} /> : null}
      {place.address ? <Body size={14}>{place.address}</Body> : null}
      {place.facts.length ? <Card style={{ gap: 12 }}>
        <Body>공간 · 방문 정보</Body>
        {place.facts.map((fact, index) => <View key={index} style={{ gap: 3 }}><Body size={14}>{fact.label}</Body><Muted>{fact.value}</Muted></View>)}
        <Pressable accessibilityRole="button" accessibilityState={{ expanded: sources }} aria-expanded={sources} style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => setSources(!sources)}><Body size={13}>{sources ? '정보 출처 접기 −' : '정보 출처·확인일 보기 ＋'}</Body></Pressable>
        {sources ? place.facts.map((fact, index) => <Pressable key={index} accessibilityRole="link" style={{ minHeight: 44, justifyContent: 'center' }} onPress={() => openSource(fact.source_url)}><Muted size={12}>{fact.label} · {fact.source_label} · {fact.checked_at} 확인 ↗</Muted></Pressable>) : null}
      </Card> : null}
      <PlaceHours key={`${place.place_id}:${context.date}`} place={{ name: place.name, hours: place.hours, place_group: place.place_group }} compact />
      <Button title="네이버 지도 열기" variant="outline" onPress={() => { const url = naverMapUrl(place.name); if (url) void Linking.openURL(url).then(() => { void track('map_open', { place_id: place.place_id, surface: 'browse', request_id: request }); }).catch(() => setError('지도를 열지 못했어요.')); }} />
      {error ? <ErrorBox message={error} /> : null}
      <Card style={{ gap: 12 }}><Body>내 취향과 맞는지도 알아볼까요?</Body><Muted size={12}>위의 장소 정보는 맞춤 설정 없이 볼 수 있어요. 체형·색조·성향 정합도는 원하는 정보를 입력한 뒤 확인할 수 있어요.</Muted><BrowseCustomize context={context} /></Card>
    </> : null}
  </Screen>;
}
