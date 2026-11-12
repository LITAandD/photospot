import type { RecommendationItem, RecommendationList } from '@photospot/client';
import type { BrowseContext } from './browse-context';
export type PublicPlace = { place_id: string; name: string; place_group: RecommendationItem['place_group']; address: string | null;
  cover_photo: RecommendationItem['cover_photo']; distance_m: number; browse_origin: NonNullable<RecommendationList['browse_origin']>;
  hours: RecommendationItem['hours']; facts: NonNullable<RecommendationItem['public_facts']> };
export class BrowseError extends Error { constructor(message: string, readonly status: number) { super(message); } }
export async function fetchBrowse<T>(context: BrowseContext, detail = false): Promise<T> {
  const base = (process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? '').replace(/\/$/, '');
  const path = detail ? `/preview/browse/${encodeURIComponent(context.place ?? '')}` : '/preview/browse';
  const controller = new AbortController(), timer = setTimeout(() => controller.abort(), 20000);
  try {
    const response = await fetch(`${base}${path}?city=${context.city}&visit_date=${context.date}`, { credentials: 'omit', signal: controller.signal });
    if (!response.ok) throw new BrowseError(response.status === 404 ? '선택한 도시에서 이 장소를 찾지 못했어요. 목록에서 다른 장소를 골라 주세요.' : '장소를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.', response.status);
    return await response.json() as T;
  } finally { clearTimeout(timer); }
}
