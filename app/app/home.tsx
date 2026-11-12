import { browseArea, browseContext, browseHref } from "@/browse-context";
import { type RecommendationItem, type TimeSlot, type PlaceGroup } from "@photospot/client";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useEffect, useMemo, useRef, useState } from "react";
import { ActivityIndicator, Linking, Pressable, ScrollView, StyleSheet, Text, View } from "react-native";

import { api, today } from "@/api";
import { Body, Button, Card, Chip, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { CalendarField } from "@/components/calendar-field";
import { PlaceRecommendation } from "@/components/place-recommendation";
import { ScoringGuide } from "@/components/score-explanation";
import { errorMessage, useAsync, useRefocus } from "@/hooks";
import { colors, fonts } from "@/theme";
import { PLACE_GROUPS, placeGroupLabel } from "@/place-groups";
import { SponsoredPlaces } from '@/components/sponsored-places';
import { StartingPlacePicker } from '@/components/starting-place-picker';
import { StartOver } from '@/components/start-over';
import { getCurrentLocation } from '@/current-location';
import { readFlag, writeFlag } from '@/local-flags';
import { measuredRecommendations } from '@/analytics';
import { CardExposure } from '@/components/card-exposure';
import { DEFAULT_PHOTO_READY_AREA, nearestSupportedPreset, SUPPORTED_REGIONS } from '@/recommendation-regions';
import { createStartingPlace, INITIAL_STARTING_PLACE, type StartingPlaceState } from '@/starting-place';

/** 기기에 남기는 플래그 이름: 위치정보 이용 동의, 베타 안내 닫기 */
const LOCATION_CONSENT = "location-consent", BETA_BANNER = "beta-banner-dismissed";

/** 스토어 구매 상태 동기화(느린 외부 호출)는 앱 실행당 한 번만. 이후 돌아올 때는 저장된 상태만 읽는다 */
let billingSynced = false;
async function loadBilling() {
  const status = await api.billing();
  if (!status.configured || billingSynced) return status;
  billingSynced = true;
  return api.syncBilling().catch(() => status);
}

export default function Home() {
  const router = useRouter();
  const params = useLocalSearchParams();
  const context = browseContext(params, today());
  const initialPlace = context ? browseArea(context.city) : DEFAULT_PHOTO_READY_AREA;
  const appliedContext = useRef(context ? `${context.city}:${context.date}` : "");
  // 기본 시작 장소는 사진이 준비된 프리셋(종로·북촌). 현위치는 '내 주변에서 찾기' → 위치정보 동의 뒤에만 조회한다
  const [location, setLocation] = useState<StartingPlaceState>({ ...INITIAL_STARTING_PLACE, place: initialPlace });
  const startingPlace = useMemo(() => createStartingPlace(async () => {
    const position = await getCurrentLocation();
    // 수집 반경 밖 좌표는 추천 0건이므로 쓰지 않고 지역 선택을 안내한다
    if (!nearestSupportedPreset(position.lat, position.lng)) throw new Error(`현위치는 아직 추천하지 않는 지역이에요. 지금은 ${SUPPORTED_REGIONS} 지역을 추천하니 아래에서 가까운 곳을 골라 주세요.`);
    return position;
  }, setLocation, 12000, initialPlace), []);
  const [locationConsent, setLocationConsent] = useState(false);
  const [betaDismissed, setBetaDismissed] = useState<boolean | null>(null);
  const pos = location.place;
  const [linkError, setLinkError] = useState<string | null>(null);
  const [date, setDate] = useState(context?.date ?? today());
  useEffect(() => {
    const key = context ? `${context.city}:${context.date}` : '';
    if (context && key !== appliedContext.current) {
      appliedContext.current = key;
      startingPlace.select(browseArea(context.city));
      setDate(context.date);
    }
  }, [context?.city, context?.date, startingPlace]);
  const [invitationDismissed, setInvitationDismissed] = useState(false);
  const [radiusM, setRadius] = useState(5000);
  const [timeSlot, setTimeSlot] = useState<TimeSlot | undefined>();
  const [placeGroup, setPlaceGroup] = useState<PlaceGroup>("all");
  const [revision, setRevision] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [photoOnly,setPhotoOnly] = useState(false);
  const [minFit,setMinFit] = useState(0);
  useEffect(() => {
    let active = true;
    void Promise.all([readFlag(LOCATION_CONSENT), readFlag(BETA_BANNER)]).then(([consent, beta]) => { if (active) { setLocationConsent(consent); setBetaDismissed(beta); } });
    return () => { active = false; startingPlace.dispose(); };
  }, [startingPlace]);
  // 상세에서 돌아올 때만 새로고침 (첫 마운트는 아래 useAsync가 이미 불러온다). 이전 결과는 유지돼 화면·스크롤이 그대로다
  useRefocus(() => setRevision((v) => v + 1));

  const billing = useAsync(loadBilling, [], revision);
  const premium = !!billing.data?.premium;
  const billingKnown = !!billing.data || !!billing.error;
  // Plus 전용 필터는 실제 값이 바뀔 때만 다시 요청한다 (premium 확인만으로는 재요청하지 않음)
  const photoFilter = premium && photoOnly, fitFilter = premium ? minFit : 0;
  const home = useAsync(() => pos ? measuredRecommendations(() => api.getRecommendations({ ...pos, date, radiusM, timeSlot, placeGroup, useSaju: false, photoOnly: photoFilter, minFit: fitFilter }), "home") : Promise.resolve(null), [pos?.lat, pos?.lng, date, radiusM, timeSlot, placeGroup, photoFilter, fitFilter], revision);
  // 요청 ID로 실제 카드 노출을 연결한다. 데이터 갱신을 첫 카드 노출로 세지 않는다.
  const requestId = (home.data as (typeof home.data & { analytics_request_id?: string }))?.analytics_request_id;
  // 두 광고 자리(우선 추천·배너)가 같은 조회를 공유한다. Plus 여부를 확인한 뒤 한 번만 요청
  const ads = useAsync(() => pos && billingKnown && !premium ? api.sponsorships({ ...pos, radiusM, placeGroup }) : Promise.resolve(null), [pos?.lat, pos?.lng, radiusM, placeGroup, billingKnown, premium], revision);
  const open = (item: RecommendationItem) =>
    router.push({ pathname: "/place/[id]", params: { id: item.place_id, rec: String(item.recommendation_id), date, spot: item.spot_id, scene: item.scene_id, saju: "0", request: requestId } });
  const addSaju = () => { if (pos) router.push({ pathname: "/saju", params: { date, lat: String(pos.lat), lng: String(pos.lng), radius: String(radiusM), label: pos.label, group: placeGroup, ...(timeSlot ? { time: timeSlot } : {}) } }); };

  return (
    <Screen style={{ paddingTop: 12, gap: 18 }}>
      <View style={s.navigation}>
        <StartOver />
        <View style={s.navLinks}>
          <Pressable onPress={() => router.push("/saved")} accessibilityRole="button" style={s.navButton}><Text style={s.filterText}>♡ 저장한 장소</Text></Pressable>
          <Pressable onPress={() => router.push("/settings")} accessibilityRole="button" style={s.navButton}><Text style={s.filterText}>내 정보 · 설정</Text></Pressable>
        </View>
      </View>
      {betaDismissed === false ? <View style={s.beta}>
        <Text style={s.betaText}>지금은 {SUPPORTED_REGIONS} 지역 베타예요</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="베타 안내 닫기" onPress={() => { setBetaDismissed(true); void writeFlag(BETA_BANNER, true); }} style={s.betaClose}><Text style={s.filterText}>닫기</Text></Pressable>
      </View> : null}
      <View style={{ gap: 6 }}>
        <Text style={s.eyebrow}>나를 위한 오늘의 배경</Text>
        <Title size={30}>오늘 어디서 찍을까요</Title>
        <Muted size={12}>{home.data?.missing_inputs.length ? `선택하면 추천에 반영해요: ${home.data.missing_inputs.join(", ")}` : "기본 추천 · 체형·퍼스널컬러·MBTI"}</Muted>
      </View>
      {context ? <View style={{ gap: 6 }}>
        <Muted size={12}>둘러보던 도시·촬영일을 이어받았어요. 아래에서 조건을 바꿀 수 있어요.</Muted>
        <Button title={context.place ? "보던 장소 다시 보기" : "공개 둘러보기로 돌아가기"} variant="outline" onPress={() => router.push(browseHref(context))} />
      </View> : null}
      <StartingPlacePicker state={location} consented={locationConsent}
        onConsent={() => { setLocationConsent(true); void writeFlag(LOCATION_CONSENT, true); void api.grantConsent("location").catch(() => { /* 동의 기록 실패는 조회를 막지 않는다 (체험은 브라우저에만 남음) */ }); }}
        onLocate={() => { void startingPlace.locate(); }} onSelect={startingPlace.select} />
      <View style={{ gap: 10 }}>
        <ScrollView horizontal showsHorizontalScrollIndicator={false} contentContainerStyle={{ gap: 8, paddingVertical: 2 }}>
          {PLACE_GROUPS.map((group) => <Chip key={group.value} label={group.label} selected={placeGroup === group.value} onPress={() => setPlaceGroup(group.value)} />)}
        </ScrollView>
        {placeGroup === "cafe" ? <Muted size={12}>카페·베이커리·식당을 함께 찾아요. 사진 명소로 선정한 곳은 상세에서 선정 이유와 사진 출처를 볼 수 있어요.</Muted> : null}
        {placeGroup === "travel" ? <Muted size={12}>자연 명소·전망대·해변·테마파크·박물관·역사 명소를 찾아요.</Muted> : null}
        {placeGroup === "festival" ? <Muted size={12}>축제장·공연장·전시 공간을 찾아요. 선택한 촬영일에 행사가 열린다는 뜻은 아니며, 일정·입장 조건은 별도 확인이 필요해요.</Muted> : null}
      </View>
      <View style={s.filterRow}>
        <View style={{ flex: 1 }}><Muted size={11}>현재 적용: 기본 프로필 · 사주·일진 미반영</Muted></View>
        <Pressable accessibilityRole="button" accessibilityState={{expanded:filtersOpen}} onPress={()=>setFiltersOpen(!filtersOpen)} style={s.filterButton}><Text style={s.filterLabel}>{filtersOpen ? '검색 조건 닫기' : '촬영일·거리·시간'}</Text></Pressable>
      </View>
      {filtersOpen ? <View style={{ gap: 16 }}>
      <CalendarField value={date} onChange={setDate} />
      <Body>검색 반경</Body>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {[1000, 3000, 5000, 10000, 30000, 50000].map((r) => <Chip key={r} label={`${r / 1000}km`} selected={radiusM === r} onPress={() => setRadius(r)} />)}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {([[undefined, "전체 시간"], ["morning", "아침"], ["midday", "낮"], ["golden_hour", "골든아워"], ["night", "밤"]] as const).map(([slot, label]) => <Chip key={label} label={label} selected={timeSlot === slot} onPress={() => setTimeSlot(slot)} />)}
      </View>
      {home.data?.catalog ? <Muted size={12}>시간대는 촬영 일정 참고용이에요. 확인된 정규 영업시간을 표시하며, 임시휴무와 공휴일 운영은 달라질 수 있어요.</Muted> : null}
      </View> : null}
      {pos ? <>
      <View style={s.resultsHeader}><Text style={s.resultsTitle}>{placeGroupLabel(placeGroup)} 추천</Text><Muted size={11}>{radiusM / 1000}km · {date}</Muted></View>
      {home.loading && !home.data ? <ActivityIndicator color={colors.accentInk} /> : null}
      {home.error ? <ErrorBox message={errorMessage(home.error)} onRetry={home.reload} /> : null}
      <ScoringGuide weights={home.data?.score_weights} compact />
      {!premium ? <SponsoredPlaces items={ads.data} placement="priority"/> : null}
      {home.data?.items.some((item) => item.discovery) ? <View testID="discovery-order"><Muted size={12}>전체 정합도가 높은 순으로 추천해요. 동점이면 평가 항목이 많은 장소를 먼저 보여드려요. 산정 전인 장소는 마지막에 표시해요.</Muted></View> : null}
      {home.data?.items.length === 0 ? <View style={{ gap: 12 }}><Body>이 조건에 맞는 장소를 찾지 못했어요. 지금은 {SUPPORTED_REGIONS} 지역을 추천해요. 지역을 바꾸거나 반경을 넓혀보세요.</Body>{radiusM < 50000 ? <Button title="50km까지 넓혀 찾기" variant="outline" onPress={() => setRadius(50000)} /> : null}<Button title="프로필 수정하기" variant="outline" onPress={() => router.push("/settings")} /></View> : null}
      {home.data?.items.slice(0, 3).map((item, index) => <CardExposure key={item.place_id} placeId={item.place_id} requestId={requestId} rank={index + 1}><PlaceRecommendation item={item} onPress={() => open(item)} /></CardExposure>)}
      {premium || (home.data?.items.length ?? 0) >= 3 ? <>
      <Card style={{gap:10}}><Body>Plus · 더 세밀하게 찾기</Body>
        {premium ? <><Chip label="사진 있는 장소만" selected={photoOnly} onPress={()=>setPhotoOnly(!photoOnly)}/><View style={{flexDirection:'row',gap:8,flexWrap:'wrap'}}>{[0,50,70,90].map(n=><Chip key={n} label={n?`정합도 ${n}점 이상`:'점수 제한 없음'} selected={minFit===n} onPress={()=>setMinFit(n)}/>)}</View><Muted size={12}>정합도가 아직 계산되지 않은 장소는 점수 필터에서 제외돼요.</Muted></> : <><Muted>사진·정합도 추가 필터와 광고 없는 추천을 이용해 보세요.</Muted><Button title="Plus 살펴보기" variant="outline" onPress={()=>router.push('/support')}/></>}
      </Card>
      </> : null}
      {home.data && !invitationDismissed ? <Card style={{ gap: 12 }}>
        <Body>사주·일진 추천도 추가로 볼까요?</Body>
        <Muted>부족한 오행을 보완하는 장소와 촬영일의 일진을 다음 탭에서 확인해 보세요.</Muted>
        <Button title="사주·일진 추천 추가" onPress={addSaju} />
        <Button title="기본 추천만 볼게요" variant="outline" onPress={() => setInvitationDismissed(true)} />
      </Card> : null}
      {home.data && invitationDismissed ? <Button title="사주·일진 추천 추가" variant="outline" onPress={addSaju} /> : null}
      {home.data?.items.slice(3).map((item, index) => <CardExposure key={item.place_id} placeId={item.place_id} requestId={requestId} rank={index + 4}><PlaceRecommendation item={item} onPress={() => open(item)} /></CardExposure>)}
      {!premium ? <SponsoredPlaces items={ads.data} placement="banner"/> : null}
      <Muted size={11}>{pos.label} 주변 추천이에요. 방문 전 영업 여부와 행사 일정을 확인해 주세요.</Muted>
      {home.data?.catalog ? <Pressable style={{ minHeight: 44, justifyContent: "center" }} accessibilityRole="link" onPress={() => Linking.openURL(home.data!.catalog!.license_url).catch(() => setLinkError("출처 링크를 열지 못했어요"))}><Muted size={11}>{home.data.catalog.label} · 이용 조건</Muted></Pressable> : null}
      {linkError ? <Muted size={12}>{linkError}</Muted> : null}
      </> : null}
    </Screen>
  );
}

const s = StyleSheet.create({
  beta: { flexDirection: "row", alignItems: "center", justifyContent: "space-between", gap: 8, paddingHorizontal: 12, paddingVertical: 4, borderRadius: 10, backgroundColor: colors.accentSoft },
  betaText: { fontFamily: fonts.body, fontSize: 12, color: colors.accentInk, flexShrink: 1 },
  betaClose: { minHeight: 36, justifyContent: "center" },
  navigation: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', columnGap: 8 },
  navLinks: { flexDirection: 'row', gap: 14 },
  navButton: { minHeight: 44, justifyContent: 'center' },
  filterText: { fontFamily: fonts.medium, fontSize: 12, color: colors.muted },
  eyebrow: { fontFamily: fonts.semibold, fontSize: 11, letterSpacing: 0.4, color: colors.secondaryInk },
  filterRow: { flexDirection: 'row', alignItems: 'center', gap: 12 },
  filterButton: { minHeight: 44, justifyContent: 'center', paddingHorizontal: 12, borderRadius: 12, backgroundColor: colors.accentSoft },
  filterLabel: { fontFamily: fonts.medium, fontSize: 12, color: colors.accentInk },
  resultsHeader: { flexDirection: 'row', flexWrap: 'wrap', alignItems: 'center', justifyContent: 'space-between', gap: 6 },
  resultsTitle: { fontFamily: fonts.semibold, fontSize: 18, color: colors.ink },
});
