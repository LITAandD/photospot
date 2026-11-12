import React from 'react';
import { ActivityIndicator, View } from 'react-native';
import { useLocalSearchParams, useRouter } from 'expo-router';
import type { RecommendationList } from '@photospot/client';
import { DEMO, today } from '@/api';
import { measuredRecommendations } from '@/analytics';
import { Body, Button, Card, Chip, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { PlaceRecommendation } from '@/components/place-recommendation';
import { CardExposure } from '@/components/card-exposure';
import { CalendarField } from '@/components/calendar-field';
import { BrowseCustomize } from '@/components/browse-customization';
import { browseContext, browseDate } from '@/browse-context';
import { fetchBrowse } from '@/public-browse';
import { errorMessage, useAsync } from '@/hooks';
import { IMPORT_REGIONS } from '@/recommendation-regions';

/** Public URL contains only city/date. No profile, GPS request or implicit consent. */
export default function Browse() {
  const router = useRouter(), params = useLocalSearchParams();
  const date = browseDate(params.date, today()), context = browseContext(params, date);
  const city = context?.city;
  const result = useAsync(() => context && DEMO ? measuredRecommendations(() => fetchBrowse<RecommendationList>(context), 'browse') : Promise.resolve(null), [city, date]);
  const requestId = (result.data as (RecommendationList & { analytics_request_id?: string }) | null)?.analytics_request_id;
  return <Screen>
    <Button title="처음으로" variant="outline" onPress={() => router.replace('/')} />
    <Title>어디를 둘러볼까요</Title>
    <Muted>개인정보 입력 없이 공간 사진과 방문 정보를 살펴보세요.</Muted>
    {!DEMO ? <Muted>공개 둘러보기는 포토스팟 웹에서 이용할 수 있어요.</Muted> : <>
      <View style={{ flexDirection: 'row', gap: 8, flexWrap: 'wrap' }}>{IMPORT_REGIONS.map(region => <Chip key={region.key} label={region.name} selected={city === region.key}
        onPress={() => router.setParams({ city: region.key, date })} />)}</View>
      <CalendarField value={date} onChange={next => router.setParams({ date: next })} />
      {!city ? <Card><Body>먼저 둘러볼 도시를 선택해 주세요.</Body><Muted>서울·부산·강릉·제주의 준비된 장소를 볼 수 있어요. 현위치는 요청하지 않아요.</Muted></Card> : null}
      {city && result.loading ? <View accessibilityLiveRegion="polite" accessibilityRole="progressbar" accessibilityLabel="선택한 도시와 날짜의 장소를 불러오는 중" style={{ gap: 8 }}>
        <ActivityIndicator /><Muted>{IMPORT_REGIONS.find(r => r.key === city)?.name} · {date} 장소를 불러오고 있어요.</Muted></View> : null}
      {result.error ? <ErrorBox message={errorMessage(result.error)} onRetry={result.reload} /> : null}
      {result.data?.browse_origin ? <Muted size={12}>{result.data.browse_origin.label} 기준점 주변 5km예요. 카드의 거리는 이 기준점에서의 직선거리이며 내 위치나 도보 거리가 아니에요. 대표사진이 있는 장소를 먼저 보여드려요.</Muted> : null}
      {result.data?.items.length === 0 && !result.loading ? <Card><Body>선택한 기준점 주변 5km에 공개할 장소 정보가 아직 없어요.</Body><Muted>도시를 바꾸거나 다른 촬영일로 다시 확인해 주세요. 실제로 방문할 곳이 없다는 뜻은 아니에요.</Muted><Button title="다시 불러오기" variant="outline" onPress={result.reload} /></Card> : null}
      {result.data?.items.map((item, index) => <CardExposure key={item.place_id} placeId={item.place_id} requestId={requestId} rank={index + 1}>
        <PlaceRecommendation item={item} publicView distanceOrigin={result.data?.browse_origin?.label} onPress={() => {
          if (context) router.push({ pathname: '/browse/[id]', params: { city, date, id: item.place_id, request: requestId } });
        }} />
      </CardExposure>)}
    </>}
    {context && DEMO ? <Card style={{ gap: 12 }}><Body>내 취향으로 더 좁혀볼까요?</Body><BrowseCustomize context={context} /></Card> : null}
    <Button title="개인정보 안내 · 통계 선택" variant="outline" onPress={() => router.push('/privacy')} />
  </Screen>;
}
