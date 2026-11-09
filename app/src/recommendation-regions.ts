export type StartingPlace = { id: string; label: string; lat: number; lng: number };
// photoReady: 이 앵커에서 5km·풀 프로필로 추천 30건을 받았을 때 사진 카드가 20건 이상인 지역.
export type RecommendationArea = StartingPlace & { name: string; description: string; photoReady: boolean };
export type ImportRegion = { key: "seoul" | "busan" | "jeju" | "gangneung"; name: string; lat: number; lng: number; radiusKm: number };

// 카탈로그 imports 테이블(2026-10-06 수집)의 중심·반경 = pipeline/place_catalog.REGIONS. 이 밖은 추천 0건이다.
export const IMPORT_REGIONS: ImportRegion[] = [
  { key: "seoul", name: "서울", lat: 37.5796, lng: 126.977, radiusKm: 18 },
  { key: "busan", name: "부산", lat: 35.1587, lng: 129.1604, radiusKm: 18 },
  { key: "jeju", name: "제주", lat: 33.4996, lng: 126.5312, radiusKm: 20 },
  { key: "gangneung", name: "강릉", lat: 37.7519, lng: 128.8761, radiusKm: 15 },
];

/** 화면 문구용 요약. 서귀포·성산은 프리셋만 있고 아직 수집 반경 밖이라 '일부'로 적는다. */
export const SUPPORTED_REGIONS = "서울·부산·강릉·제주 일부";

// Search anchors, not administrative boundaries. Nearby results use the chosen radius.
// photoReady 값은 2026-11-09 카탈로그에서 계산한 결과를 고정한 것(5km 풀 프로필 상위 30건 중 사진 카드 수:
// 종로 30 · 성수 25 · 홍대 30 · 여의도 23 · 잠실 16 · 남산 30 · 강남 16 · 해운대 8 · 광안리 10 · 남포 9 · 영도 10 ·
// 송정 3 · 경포 4 · 안목 3 · 주문진 0 · 제주시 3 · 애월 0 · 서귀포 0 · 성산 0). 다시 계산하려면 저장소 루트에서:
//   PLACE_CATALOG_DB=catalog/places.sqlite3 RATE_LIMIT_PREVIEW_PER_MIN=0 python - <<'EOF'
//   from fastapi.testclient import TestClient; from api.preview import app; c = TestClient(app)
//   P = {'gender':'female','height_cm':165,'pc_season':'spring_warm','body_type':'straight','mbti':'INFP'}
//   for lat, lng, name in [(37.5796,126.977,'종로'), ...]:   # RECOMMENDATION_REGIONS의 좌표
//       items = c.post('/preview/evaluate', json={'profile':P,'visit_date':'2026-11-10','lat':lat,'lng':lng,'radius_m':5000}).json()['recommendations']['items']
//       print(name, sum(1 for i in items if i['cover_photo']), '>= 20 → photoReady')
//   EOF
export const RECOMMENDATION_REGIONS: { name: string; areas: RecommendationArea[] }[] = [
  { name: "서울", areas: [
    { id: "seoul-jongno", name: "종로·북촌", label: "서울 종로·북촌", description: "고궁 · 한옥 · 골목", lat: 37.5796, lng: 126.977, photoReady: true },
    { id: "seoul-seongsu", name: "성수·서울숲", label: "서울 성수·서울숲", description: "카페 · 숲 · 산업 건축", lat: 37.5446, lng: 127.0438, photoReady: true },
    { id: "seoul-hongdae", name: "홍대·연남", label: "서울 홍대·연남", description: "개성 있는 골목 · 카페", lat: 37.5587, lng: 126.9245, photoReady: true },
    { id: "seoul-yeouido", name: "여의도·한강", label: "서울 여의도·한강", description: "강변 · 공원 · 도심 야경", lat: 37.5281, lng: 126.9328, photoReady: true },
    { id: "seoul-jamsil", name: "잠실·석촌호수", label: "서울 잠실·석촌호수", description: "호수 · 산책 · 스카이라인", lat: 37.5101, lng: 127.1026, photoReady: false },
    { id: "seoul-namsan", name: "남산·이태원", label: "서울 남산·이태원", description: "전망 · 언덕길 · 거리", lat: 37.5513, lng: 126.9882, photoReady: true },
    { id: "seoul-gangnam", name: "강남·코엑스", label: "서울 강남·코엑스", description: "현대 건축 · 실내 공간", lat: 37.5118, lng: 127.0592, photoReady: false },
  ] },
  { name: "부산", areas: [
    { id: "busan-haeundae", name: "해운대·미포", label: "부산 해운대·미포", description: "해변 · 해안 산책 · 야경", lat: 35.1587, lng: 129.1604, photoReady: false },
    { id: "busan-gwangalli", name: "광안리", label: "부산 광안리", description: "광안대교 · 바다 · 카페", lat: 35.1509, lng: 129.1191, photoReady: false },
    { id: "busan-nampo", name: "남포·감천", label: "부산 남포·감천", description: "원도심 · 시장 · 마을", lat: 35.0975, lng: 129.0230, photoReady: false },
    { id: "busan-yeongdo", name: "영도·흰여울", label: "부산 영도·흰여울", description: "해안 절벽 · 골목 · 전망", lat: 35.0774, lng: 129.0457, photoReady: false },
    { id: "busan-songjeong", name: "송정·기장 해안", label: "부산 송정·기장 해안", description: "해변 · 해안 사찰 · 일출", lat: 35.1805, lng: 129.2033, photoReady: false },
  ] },
  { name: "강릉", areas: [
    { id: "gangneung-gyeongpo", name: "경포·초당", label: "강릉 경포·초당", description: "호수 · 해변 · 소나무", lat: 37.7953, lng: 128.9090, photoReady: false },
    { id: "gangneung-anmok", name: "안목·남항진", label: "강릉 안목·남항진", description: "커피거리 · 바다 · 다리", lat: 37.7727, lng: 128.9482, photoReady: false },
    { id: "gangneung-jumunjin", name: "주문진", label: "강릉 주문진", description: "방파제 · 항구 · 해변", lat: 37.8799, lng: 128.8342, photoReady: false },
  ] },
  { name: "제주", areas: [
    { id: "jeju-city", name: "제주시", label: "제주 제주시", description: "원도심 · 용두암 · 해안도로", lat: 33.4996, lng: 126.5312, photoReady: false },
    { id: "jeju-aewol", name: "애월", label: "제주 애월", description: "해안 카페 · 한담 산책로", lat: 33.4631, lng: 126.3100, photoReady: false },
    // 제주시 중심 20km 수집 반경 밖. 수집 전까지는 결과가 없으므로 '준비 중'으로 안내한다.
    { id: "jeju-seogwipo", name: "서귀포", label: "제주 서귀포", description: "폭포 · 올레길 · 수집 준비 중", lat: 33.2541, lng: 126.5601, photoReady: false },
    { id: "jeju-seongsan", name: "성산", label: "제주 성산", description: "일출봉 · 광치기해변 · 수집 준비 중", lat: 33.4587, lng: 126.9424, photoReady: false },
  ] },
];

export const ALL_AREAS: RecommendationArea[] = RECOMMENDATION_REGIONS.flatMap((region) => region.areas);

export function distanceKm(a: { lat: number; lng: number }, b: { lat: number; lng: number }): number {
  const rad = Math.PI / 180;
  const h = Math.sin(((b.lat - a.lat) * rad) / 2) ** 2
    + Math.cos(a.lat * rad) * Math.cos(b.lat * rad) * Math.sin(((b.lng - a.lng) * rad) / 2) ** 2;
  return 6371 * 2 * Math.asin(Math.min(1, Math.sqrt(h)));
}

/** 좌표가 들어 있는 수집 지역. 모든 수집 반경 밖이면 null (= 추천 0건이 나올 좌표). */
export function importRegionFor(lat: number, lng: number): ImportRegion | null {
  return IMPORT_REGIONS.find((region) => distanceKm(region, { lat, lng }) <= region.radiusKm) ?? null;
}

/**
 * 수집 반경 안이면 가장 가까운 프리셋, 밖이면 null.
 * 밖일 때 UI는 SUPPORTED_REGIONS 안내와 함께 photoReady 프리셋(종로·북촌 등)을 기본 제안한다.
 */
export function nearestSupportedPreset(lat: number, lng: number): RecommendationArea | null {
  if (!Number.isFinite(lat) || !Number.isFinite(lng) || !importRegionFor(lat, lng)) return null;
  return ALL_AREAS.reduce((best, area) => (distanceKm(area, { lat, lng }) < distanceKm(best, { lat, lng }) ? area : best));
}

/** 사진 준비가 끝난 프리셋 중 첫 번째(종로·북촌). 미지원 좌표의 기본 시작점으로 쓴다. */
export const DEFAULT_PHOTO_READY_AREA: RecommendationArea = ALL_AREAS.find((area) => area.photoReady)!;
