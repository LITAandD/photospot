export type Party = '' | 'solo' | 'pair' | 'family';
export type Goal = '' | 'portrait' | 'architecture' | 'landscape';
export type ShotQuery = { date: string; party: Party; goal: Goal; time: string; cut: string; review: string };
export type Source = { label: string; url: string; checked_at: string; valid_until: string };
export type Hours = { opens: string; closes: string; last_entry: string | null };
export type Shot = {
  cut_id: string; place_id: string; place_name: string; title: string; reason: string;
  pin: { lat: number; lng: number; standing_landmark: string; bearing_deg: number; look_toward: string; entry_instructions: string };
  framing: string; navigation_url: string; restrictions: string; light_note: string | null;
  visual: { kind: 'diagram' | 'photo'; creator: string; rights: string; image_url: string | null; source_url: string | null; license_url: string | null };
  availability: 'eligible' | 'conditional'; availability_note: string;
  place_hours: Hours[]; cut_hours: Hours[]; place_hours_note: string; cut_hours_note: string;
  sources: Source[]; field_checked_at: string;
};
export type ShotResult = { date: string; entry_ready: boolean; primary: Shot | null; alternative: Shot | null; replacement_reason: string | null;
  excluded: { cut_id: string; title: string; reason: string }[]; eligible_count: number; candidate_count: number;
  empty_message: string | null; mode: 'catalog' | 'review'; review_available: boolean };
export function shotParams(query: ShotQuery): URLSearchParams {
  const out = new URLSearchParams({ date: query.date, city: 'seoul' });
  for (const key of ['party', 'goal', 'time', 'cut', 'review'] as const) if (query[key]) out.set(key, query[key]);
  return out;
}
export async function fetchShots(query: ShotQuery): Promise<ShotResult> {
  const p = new URLSearchParams({ visit_date: query.date });
  for (const key of ['party', 'goal', 'cut'] as const) if (query[key]) p.set(key, query[key]);
  if (query.time) p.set('arrival', query.time);
  if (query.review) p.set('review_case', query.review);
  const base = (process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? '').replace(/\/$/, '');
  const controller = new AbortController(), timeout = setTimeout(() => controller.abort(), 20000);
  try {
    // Public endpoint needs no app login. Same-origin cookies still carry Vercel
    // preview access; never send credentials to a separately configured origin.
    const r = await fetch(`${base}/preview/shots?${p}`, { credentials: 'same-origin', signal: controller.signal });
    if (!r.ok) throw new Error(r.status === 404 ? '이 컷 또는 검토용 화면을 찾지 못했어요. 컷 선택을 해제하고 다시 확인해 주세요.' : '촬영 안내를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
    return await r.json();
  } catch (error) {
    if (error instanceof Error && error.name === 'AbortError') throw new Error('촬영 안내 확인이 지연되고 있어요. 잠시 후 다시 시도해 주세요.');
    if (error instanceof TypeError) throw new Error('촬영 안내에 연결하지 못했어요. 인터넷 연결을 확인하고 다시 시도해 주세요.');
    throw error;
  } finally { clearTimeout(timeout); }
}
