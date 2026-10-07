import { type RecommendationItem, type TimeSlot, type PlaceGroup } from "@photospot/client";
import * as Location from "expo-location";
import { useFocusEffect, useRouter } from "expo-router";
import React, { useCallback, useEffect, useState } from "react";
import { ActivityIndicator, Linking, Pressable, StyleSheet, Text, View } from "react-native";

import { api, DEMO, today } from "@/api";
import { Body, Button, Card, Chip, ErrorBox, Field, Muted, Screen, Title } from "@/components/ui";
import { PlaceRecommendation } from "@/components/place-recommendation";
import { ScoringGuide } from "@/components/score-explanation";
import { errorMessage, useAsync } from "@/hooks";
import { colors, fonts } from "@/theme";
import { PLACE_GROUPS, placeGroupLabel } from "@/place-groups";
import { SponsoredPlaces } from '@/components/sponsored-places';

const SEOUL = { lat: 37.5796, lng: 126.977 };      // 위치 권한이 없을 때 기본값 (경복궁)
const REGIONS = [
  { name: "서울", ...SEOUL }, { name: "부산", lat: 35.1587, lng: 129.1604 },
  { name: "제주", lat: 33.4996, lng: 126.5312 }, { name: "강릉", lat: 37.7519, lng: 128.8761 },
];

export default function Home() {
  const router = useRouter();
  const [pos, setPos] = useState({ ...SEOUL, label: "서울 종로" });
  const [locating, setLocating] = useState(false);
  const [locationNote, setLocationNote] = useState<string | null>(null);
  const [date, setDate] = useState(today());
  const [dateText, setDateText] = useState(date);
  const [dateError, setDateError] = useState<string | null>(null);
  const [invitationDismissed, setInvitationDismissed] = useState(false);
  const [radiusM, setRadius] = useState(5000);
  const [timeSlot, setTimeSlot] = useState<TimeSlot | undefined>();
  const [placeGroup, setPlaceGroup] = useState<PlaceGroup>("all");
  const [revision, setRevision] = useState(0);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [photoOnly,setPhotoOnly] = useState(false);
  const [minFit,setMinFit] = useState(0);
  const alive = React.useRef(true);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);
  useFocusEffect(useCallback(() => { setRevision((v) => v + 1); }, []));

  const locate = async () => {
    if (locating) return;
    setLocating(true); setLocationNote(null);
    let timer: ReturnType<typeof setTimeout> | undefined;
    try {
      const { status } = await Location.requestForegroundPermissionsAsync();
      if (status !== "granted") throw new Error("위치 권한 없이도 지역을 골라 추천받을 수 있어요.");
      const loc = await Promise.race([
        Location.getCurrentPositionAsync({ accuracy: Location.Accuracy.Balanced }),
        new Promise<never>((_, reject) => { timer = setTimeout(() => reject(new Error("위치를 찾지 못했어요. 지역을 직접 선택해 주세요.")), 10000); }),
      ]);
      if (!alive.current) return;
      const { latitude: lat, longitude: lng } = loc.coords;
      if (lat < 33 || lat > 39 || lng < 124 || lng > 132) throw new Error("현재는 국내 장소를 추천해요. 방문할 지역을 선택해 주세요.");
      setPos({ lat, lng, label: "내 위치" });
    } catch (e) {
      if (alive.current) setLocationNote(errorMessage(e));
    } finally { if (timer) clearTimeout(timer); if (alive.current) setLocating(false); }
  };

  const billing = useAsync(async()=>{const status=await api.billing();return status.configured ? api.syncBilling() : status;},[revision]);
  const premium = !!billing.data?.premium;
  const home = useAsync(() => api.getRecommendations({ ...pos, date, radiusM, timeSlot, placeGroup, useSaju: false, photoOnly: premium && photoOnly, minFit: premium ? minFit : 0 }), [pos.lat, pos.lng, date, radiusM, timeSlot, placeGroup, revision, premium, photoOnly, minFit]);
  const open = (item: RecommendationItem) =>
    router.push({ pathname: "/place/[id]", params: { id: item.place_id, rec: String(item.recommendation_id), date, spot: item.spot_id, scene: item.scene_id, saju: "0" } });
  const addSaju = () => router.push({ pathname: "/saju", params: { date, lat: String(pos.lat), lng: String(pos.lng), radius: String(radiusM), label: pos.label, group: placeGroup, ...(timeSlot ? { time: timeSlot } : {}) } });
  const applyDate = () => {
    const parsed = new Date(`${dateText}T12:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== dateText) {
      setDateError("촬영일을 YYYY-MM-DD 형식의 실제 날짜로 입력해 주세요"); return;
    }
    setDateError(null); setDate(dateText);
  };

  return (
    <Screen style={{ paddingTop: 24 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between" }}>
        <Pressable onPress={() => router.push("/saved")} accessibilityRole="button"><Text style={s.filterText}>♡ 저장한 장소</Text></Pressable>
        <Pressable onPress={() => router.push("/settings")} accessibilityRole="button"><Text style={s.filterText}>내 정보 · 설정</Text></Pressable>
      </View>
      <View style={{ gap: 4 }}>
        <Muted size={13}>{home.data?.missing_inputs.length ? `선택하면 추천에 반영해요: ${home.data.missing_inputs.join(", ")}` : "나의 포토 타입 기준"}</Muted>
        <Title size={26}>오늘 어디서 찍을까요</Title>
        <Body>기본 추천 · 체형·퍼스널컬러·MBTI</Body>
      </View>
      <Muted size={12}>정합도는 내 프로필과 확인된 사진 특징을 비교한 점수예요. 장소 상세에서 평가한 항목과 가중치를 확인할 수 있어요.</Muted>
      <Muted size={12}>현재 적용: 기본 프로필 · 사주·일진 미반영</Muted>
      <View style={{ gap: 10 }}>
        <Body>어떤 공간을 찾으세요?</Body>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {PLACE_GROUPS.map((group) => <Chip key={group.value} label={group.label} selected={placeGroup === group.value} onPress={() => setPlaceGroup(group.value)} />)}
        </View>
        {placeGroup === "travel" ? <Muted size={12}>자연 명소·전망대·해변·테마파크·박물관·역사 명소를 찾아요.</Muted> : null}
        {placeGroup === "festival" ? <Muted size={12}>축제장·공연장·전시 공간을 찾아요. 선택한 촬영일에 행사가 열린다는 뜻은 아니며, 일정·입장 조건은 별도 확인이 필요해요.</Muted> : null}
      </View>
      <Button title={filtersOpen ? "검색 조건 닫기" : "지역·시간 바꾸기"} variant="outline" onPress={() => setFiltersOpen(!filtersOpen)} />
      {filtersOpen ? <View style={{ gap: 16 }}>
      <Field label="촬영일" value={dateText} onChange={setDateText} placeholder="YYYY-MM-DD" />
      {dateError ? <ErrorBox message={dateError} /> : null}
      <Button title="촬영일 적용" variant="outline" onPress={applyDate} />
      <View style={{ flexDirection: "row", gap: 8, flexWrap: "wrap" }}>
        {REGIONS.map((r) => <Chip key={r.name} label={r.name} selected={pos.lat === r.lat && pos.lng === r.lng} onPress={() => { setPos({ lat: r.lat, lng: r.lng, label: r.name }); setLocationNote(null); }} />)}
      </View>
      <Button title="내 위치로 찾기" variant="outline" onPress={locate} loading={locating} />
      {locationNote ? <Muted size={13}>{locationNote}</Muted> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {[5000, 10000, 30000, 50000].map((r) => <Chip key={r} label={`${r / 1000}km`} selected={radiusM === r} onPress={() => setRadius(r)} />)}
      </View>
      <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
        {([[undefined, "전체 시간"], ["morning", "아침"], ["midday", "낮"], ["golden_hour", "골든아워"], ["night", "밤"]] as const).map(([slot, label]) => <Chip key={label} label={label} selected={timeSlot === slot} onPress={() => setTimeSlot(slot)} />)}
      </View>
      {home.data?.catalog ? <Muted size={12}>시간대는 촬영 일정 참고용이에요. 확인된 정규 영업시간을 표시하며, 임시휴무와 공휴일 운영은 달라질 수 있어요.</Muted> : null}
      </View> : null}
      <Muted size={12}>{pos.label} 주변 {radiusM / 1000}km · {placeGroupLabel(placeGroup)} · {date} 기준. 방문 전 영업 여부와 행사 일정을 확인해 주세요.</Muted>
      {home.loading ? <ActivityIndicator color={colors.accent} /> : null}
      {home.error ? <ErrorBox message={errorMessage(home.error)} onRetry={home.reload} /> : null}
      <ScoringGuide weights={home.data?.score_weights} />
      <Card style={{gap:10}}><Body>Plus · 더 세밀하게 찾기</Body>
        {premium ? <><Chip label="사진 있는 장소만" selected={photoOnly} onPress={()=>setPhotoOnly(!photoOnly)}/><View style={{flexDirection:'row',gap:8,flexWrap:'wrap'}}>{[0,50,70,90].map(n=><Chip key={n} label={n?`정합도 ${n}점 이상`:'점수 제한 없음'} selected={minFit===n} onPress={()=>setMinFit(n)}/>)}</View><Muted size={12}>정합도가 아직 계산되지 않은 장소는 점수 필터에서 제외돼요.</Muted></> : <><Muted>사진·정합도 추가 필터와 광고 없는 추천을 이용해 보세요.</Muted><Button title="Plus 살펴보기" variant="outline" onPress={()=>router.push('/support')}/></>}
      </Card>
      {!premium ? <SponsoredPlaces query={{...pos,radiusM,placeGroup}} placement="priority" revision={revision}/> : null}
      {home.data?.items.some((item) => item.discovery) ? <View testID="discovery-order"><Muted size={12}>사진 있는 장소를 먼저 보여드려요. 카페는 확인된 리뷰·게시물 지표도 추천 순서에 반영해요.</Muted></View> : null}
      {home.data?.items.length === 0 ? <View style={{ gap: 12 }}><Body>이 조건에 맞는 장소를 찾지 못했어요. 지역을 바꾸거나 반경을 넓혀보세요.</Body>{radiusM < 50000 ? <Button title="50km까지 넓혀 찾기" variant="outline" onPress={() => setRadius(50000)} /> : null}<Button title="프로필 수정하기" variant="outline" onPress={() => router.push("/settings")} /></View> : null}
      {home.data?.items.slice(0, 3).map((item) => <PlaceRecommendation key={item.recommendation_id} item={item} onPress={() => open(item)} />)}
      {home.data && !invitationDismissed ? <Card style={{ gap: 12 }}>
        <Body>사주·일진 추천도 추가로 볼까요?</Body>
        <Muted>부족한 오행을 보완하는 장소와 촬영일의 일진을 다음 탭에서 확인해 보세요.</Muted>
        <Button title="사주·일진 추천 추가" onPress={addSaju} />
        <Button title="기본 추천만 볼게요" variant="outline" onPress={() => setInvitationDismissed(true)} />
      </Card> : null}
      {home.data && invitationDismissed ? <Button title="사주·일진 추천 추가" variant="outline" onPress={addSaju} /> : null}
      {home.data?.items.slice(3).map((item) => <PlaceRecommendation key={item.recommendation_id} item={item} onPress={() => open(item)} />)}
      {!premium ? <SponsoredPlaces query={{...pos,radiusM,placeGroup}} placement="banner" revision={revision}/> : null}
      {home.data?.catalog ? <Pressable accessibilityRole="link" onPress={() => Linking.openURL(home.data!.catalog!.license_url).catch(() => setLocationNote("출처 링크를 열지 못했어요"))}><Muted size={11}>{home.data.catalog.label} · 이용 조건</Muted></Pressable> : null}
    </Screen>
  );
}

const s = StyleSheet.create({
  filterText: { fontFamily: fonts.body, fontSize: 13, color: colors.ink },
});
