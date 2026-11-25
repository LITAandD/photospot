import React from 'react';
import { useRouter } from 'expo-router';
import type { RecommendationItem } from '@photospot/client';
import { CardExposure } from './card-exposure';
import { PlaceRecommendation } from './place-recommendation';

/** Local filter/help changes need not redraw every card or rebuild its exposure observer. */
export const RecommendationRow = React.memo(function RecommendationRow({ item, date, requestId, rank, useSaju = false }: {
  item: RecommendationItem; date: string; requestId?: string; rank: number; useSaju?: boolean;
}) {
  const router = useRouter();
  return <CardExposure placeId={item.place_id} requestId={requestId} rank={rank}>
    <PlaceRecommendation item={item} onPress={() => router.push({ pathname: '/place/[id]', params: {
      id: item.place_id, rec: String(item.recommendation_id), date, spot: item.spot_id,
      scene: item.scene_id, saju: useSaju ? '1' : '0', request: requestId,
    } })} />
  </CardExposure>;
});
