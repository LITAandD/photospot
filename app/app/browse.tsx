import React, { useState } from 'react';
import { ActivityIndicator, Linking, Modal, View } from 'react-native';
import { useRouter } from 'expo-router';
import { naverMapUrl, type RecommendationItem, type RecommendationList } from '@photospot/client';
import { DEMO, today } from '@/api';
import { measuredRecommendations, track } from '@/analytics';
import { Body, Button, Card, Chip, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { PlaceRecommendation } from '@/components/place-recommendation';
import { PlacePhoto, PhotoCredit } from '@/components/place-photo';
import { PlaceHours } from '@/components/place-hours';
import { CardExposure } from '@/components/card-exposure';
import { CalendarField } from '@/components/calendar-field';
import { errorMessage, useAsync } from '@/hooks';
import { IMPORT_REGIONS } from '@/recommendation-regions';

/** Public web catalog only. Never reads a profile or asks for GPS, and never creates a session/login. */
export default function Browse() {
  const router = useRouter();
  const [city, setCity] = useState<string | null>(null);
  const [date, setDate] = useState(today());
  const [selected, setSelected] = useState<RecommendationItem | null>(null);
  const [linkError, setLinkError] = useState<string | null>(null);
  const result = useAsync(() => city && DEMO ? measuredRecommendations(async () => {
    const base = (process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? '').replace(/\/$/, '');
    const response = await fetch(`${base}/preview/browse?city=${encodeURIComponent(city)}&visit_date=${encodeURIComponent(date)}`, { credentials: 'omit' });
    if (!response.ok) throw new Error('장소를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
    return await response.json() as RecommendationList;
  }, 'browse') : Promise.resolve(null), [city, date]);
  const requestId = (result.data as (RecommendationList & { analytics_request_id?: string }) | null)?.analytics_request_id;
  return <Screen>
    <Button title="처음으로" variant="outline" onPress={() => router.replace('/')} />
    <Title>어디를 둘러볼까요</Title>
    <Muted>개인정보 입력 없이 도시의 촬영 장소를 미리 살펴보세요. 개인 정합도는 계산하지 않으며, 거리는 선택한 도시의 기준 지점에서 계산해요.</Muted>
    {!DEMO ? <Muted>공개 둘러보기는 포토스팟 웹에서 이용할 수 있어요.</Muted> : <>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>{IMPORT_REGIONS.map(region => <Chip key={region.key} label={region.name} selected={city === region.key} onPress={() => { setSelected(null); setCity(region.key); }} />)}</View>
      <CalendarField value={date} onChange={setDate} />
      {result.loading ? <ActivityIndicator /> : null}
      {result.error ? <ErrorBox message={errorMessage(result.error)} onRetry={result.reload} /> : null}
      {result.data?.items.length === 0 ? <Body>이 지역에서 준비된 장소가 없어요. 다른 도시를 선택해 주세요.</Body> : null}
      {result.data?.items.map((item, index) => <CardExposure key={item.place_id} placeId={item.place_id} active={!selected} requestId={requestId} rank={index + 1}>
        <PlaceRecommendation item={item} onPress={() => { setSelected(item); void track('place_view', { place_id: item.place_id, surface: 'browse', request_id: requestId ?? '' }); }} />
      </CardExposure>)}
    </>}
    <Card style={{ gap: 12 }}><Body>내 취향에 맞는 장소도 찾아볼까요?</Body><Muted>맞춤 설정은 선택이에요. 이용 동의와 만 14세 이상 확인 후 원하는 정보만 입력할 수 있어요.</Muted>
      <Button title="맞춤 추천 시작하기" onPress={() => router.push('/login')} />
      <Button title="개인정보 안내 · 통계 선택" variant="outline" onPress={() => router.push('/privacy')} />
    </Card>
    <Modal visible={!!selected} animationType="slide" onRequestClose={() => setSelected(null)}>
      <Screen>{selected ? <>
        <Button title="둘러보기로 돌아가기" variant="outline" onPress={() => setSelected(null)} />
        <Title>{selected.place_name}</Title>
        <PlacePhoto photo={selected.cover_photo} fit="contain" style={{ width: '100%', aspectRatio: 1 }} label={selected.place_name} />
        {selected.cover_photo ? <PhotoCredit photo={selected.cover_photo} /> : null}
        <PlaceHours place={{ name: selected.place_name, hours: selected.hours, place_group: selected.place_group }} />
        <Button title="네이버 지도" variant="outline" onPress={() => { const url = naverMapUrl(selected.place_name); if (url) void Linking.openURL(url).then(() => { void track('map_open', { place_id: selected.place_id, surface: 'browse' }); }).catch(() => setLinkError('지도를 열지 못했어요.')); }} />
        {linkError ? <ErrorBox message={linkError} /> : null}
        <Button title="맞춤 설정 후 더 자세히 보기" onPress={() => { setSelected(null); router.push('/login'); }} />
      </> : null}</Screen>
    </Modal>
  </Screen>;
}
