export type StartingPlace = { id: string; label: string; lat: number; lng: number };
export type RecommendationArea = StartingPlace & { name: string; description: string };

// Search anchors, not administrative boundaries. Nearby results use the chosen radius.
export const RECOMMENDATION_REGIONS: { name: string; areas: RecommendationArea[] }[] = [
  { name: "서울", areas: [
    { id: "seoul-jongno", name: "종로·북촌", label: "서울 종로·북촌", description: "고궁 · 한옥 · 골목", lat: 37.5796, lng: 126.977 },
    { id: "seoul-seongsu", name: "성수·서울숲", label: "서울 성수·서울숲", description: "카페 · 숲 · 산업 건축", lat: 37.5446, lng: 127.0438 },
    { id: "seoul-hongdae", name: "홍대·연남", label: "서울 홍대·연남", description: "개성 있는 골목 · 카페", lat: 37.5587, lng: 126.9245 },
    { id: "seoul-yeouido", name: "여의도·한강", label: "서울 여의도·한강", description: "강변 · 공원 · 도심 야경", lat: 37.5281, lng: 126.9328 },
    { id: "seoul-jamsil", name: "잠실·석촌호수", label: "서울 잠실·석촌호수", description: "호수 · 산책 · 스카이라인", lat: 37.5101, lng: 127.1026 },
    { id: "seoul-namsan", name: "남산·이태원", label: "서울 남산·이태원", description: "전망 · 언덕길 · 거리", lat: 37.5513, lng: 126.9882 },
    { id: "seoul-gangnam", name: "강남·코엑스", label: "서울 강남·코엑스", description: "현대 건축 · 실내 공간", lat: 37.5118, lng: 127.0592 },
  ] },
  { name: "부산", areas: [
    { id: "busan-haeundae", name: "해운대·미포", label: "부산 해운대·미포", description: "해변 · 해안 산책 · 야경", lat: 35.1587, lng: 129.1604 },
    { id: "busan-gwangalli", name: "광안리", label: "부산 광안리", description: "광안대교 · 바다 · 카페", lat: 35.1509, lng: 129.1191 },
    { id: "busan-nampo", name: "남포·감천", label: "부산 남포·감천", description: "원도심 · 시장 · 마을", lat: 35.0975, lng: 129.0230 },
    { id: "busan-yeongdo", name: "영도·흰여울", label: "부산 영도·흰여울", description: "해안 절벽 · 골목 · 전망", lat: 35.0774, lng: 129.0457 },
    { id: "busan-songjeong", name: "송정·기장 해안", label: "부산 송정·기장 해안", description: "해변 · 해안 사찰 · 일출", lat: 35.1805, lng: 129.2033 },
  ] },
  { name: "강릉", areas: [
    { id: "gangneung-gyeongpo", name: "경포·초당", label: "강릉 경포·초당", description: "호수 · 해변 · 소나무", lat: 37.7953, lng: 128.9090 },
    { id: "gangneung-anmok", name: "안목·남항진", label: "강릉 안목·남항진", description: "커피거리 · 바다 · 다리", lat: 37.7727, lng: 128.9482 },
    { id: "gangneung-jumunjin", name: "주문진", label: "강릉 주문진", description: "방파제 · 항구 · 해변", lat: 37.8799, lng: 128.8342 },
  ] },
];
