import type { TimeSlot, PlaceGroup } from "@photospot/client";
import { useFocusEffect, useLocalSearchParams, useRouter } from "expo-router";
import React, { useCallback, useState } from "react";
import { ActivityIndicator, Linking, Pressable, Text, View } from "react-native";
import { api, today } from "@/api";
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { ShootPlan } from "@/components/shoot-plan";
import { PlaceRecommendation } from "@/components/place-recommendation";
import { errorMessage, useAsync } from "@/hooks";
import { colors, fonts } from "@/theme";
import { PLACE_GROUPS, placeGroupLabel } from "@/place-groups";

function coordinate(value: string | undefined, fallback: number, low: number, high: number) {
  const n = Number(value);
  return value && Number.isFinite(n) && n >= low && n <= high ? n : fallback;
}

export default function SajuRecommendations() {
  const router = useRouter();
  const params = useLocalSearchParams<{ date?: string; lat?: string; lng?: string; radius?: string; label?: string; time?: string; group?: string }>();
  const [date, setDate] = useState(params.date ?? today());
  const [applied, setApplied] = useState(false);
  const [revision, setRevision] = useState(0);
  useFocusEffect(useCallback(() => { setRevision((v) => v + 1); }, []));
  const back = () => router.canGoBack() ? router.back() : router.replace("/home");
  const search = { lat: coordinate(params.lat, 37.5796, 33, 39), lng: coordinate(params.lng, 126.977, 124, 132),
    placeGroup: PLACE_GROUPS.find((g) => g.value === params.group)?.value ?? "all",
    radiusM: Math.round(coordinate(params.radius, 5000, 500, 50000)),
    timeSlot: (["morning", "midday", "golden_hour", "night"].includes(params.time ?? "") ? params.time : undefined) as TimeSlot | undefined };
  return <Screen>
    <View accessibilityRole="tablist" style={{ flexDirection: "row", gap: 12 }}>
      <Pressable accessibilityRole="tab" accessibilityState={{ selected: false }} aria-selected={false} onPress={back}
        style={{ flex: 1, paddingVertical: 16, borderBottomWidth: 2, borderColor: colors.line }}>
        <Text style={{ fontFamily: fonts.body, color: colors.muted, textAlign: "center" }}>기본 추천</Text>
      </Pressable>
      <View accessibilityRole="tab" accessibilityState={{ selected: true }} aria-selected={true}
        style={{ flex: 1, paddingVertical: 16, borderBottomWidth: 2, borderColor: colors.accent }}>
        <Text style={{ fontFamily: fonts.semibold, color: colors.accent, textAlign: "center" }}>오행·일진 추천</Text>
      </View>
    </View>
    <Title size={26}>나의 오행과 촬영일에 맞는 장소</Title>
    <Muted>{params.label ?? "선택한 지역"} 주변 {search.radiusM / 1000}km · {placeGroupLabel(search.placeGroup)} · 기본 추천과 같은 검색 범위</Muted>
    {applied ? <>
      <Button title="촬영 날짜·사주 정보 변경" variant="outline" onPress={() => setApplied(false)} />
      <Results date={date} search={search} revision={revision} onEdit={() => setApplied(false)} />
    </> : <>
      <Muted>나에게 부족한 오행과 촬영일의 일진을 함께 계산해 우선 추천할 오행과 장소를 골라요.</Muted>
      <ShootPlan date={date} revision={revision} onApply={(nextDate) => { setDate(nextDate); router.setParams({ date: nextDate }); setRevision((v) => v + 1); setApplied(true); }} />
    </>}
    <Button title="기본 추천으로 돌아가기" variant="outline" onPress={back} />
  </Screen>;
}

function Results({ date, search, revision, onEdit }: { date: string; search: { lat: number; lng: number; radiusM: number; timeSlot?: TimeSlot; placeGroup: PlaceGroup }; revision: number; onEdit: () => void }) {
  const router = useRouter();
  const [linkError, setLinkError] = useState<string | null>(null);
  const [showBasis, setShowBasis] = useState(false);
  const result = useAsync(() => api.getRecommendations({ ...search, date, useSaju: true }), [date, search.lat, search.lng, search.radiusM, search.timeSlot, search.placeGroup, revision]);
  if (result.loading) return <ActivityIndicator color={colors.accent} />;
  if (result.error) return <ErrorBox message={errorMessage(result.error)} onRetry={result.reload} />;
  const data = result.data;
  if (!data?.daily) return <Card style={{ gap: 12 }}><Body>저장된 오행 비율이 없어요. 사주 정보를 다시 계산해 주세요.</Body><Button title="사주 정보 입력" onPress={onEdit} /></Card>;
  const daily = data.daily;
  return <>
    <Card style={{ gap: 8 }}>
      <Body>{daily.deficient_labels.length ? `보완할 오행 · ${daily.deficient_labels.join("·")} (각 ${daily.minimum_percent}%)` : "오행 비율이 균형을 이루고 있어요"}</Body>
      <Body>{date} · {daily.pillar}일 · 일진 천간 {daily.day_label}</Body>
      <Body>종합 판단 우선 추천 · {(daily.target_labels ?? []).join("·")}</Body>
      <Muted size={13}>개인 보완 70% + 일진 관계 30%로 함께 판단했어요. 아래 장소는 이 종합 점수가 높은 순서예요.</Muted>
      <Button title={showBasis ? "판단 기준 접기" : "종합 판단 기준 보기"} variant="outline" onPress={() => setShowBasis(!showBasis)} />
      {showBasis ? <>
        <Muted size={12}>{daily.note}</Muted>
        {(daily.element_priorities ?? []).filter((p) => p.is_candidate).map((p) => <View key={p.element} style={{ gap: 3 }}>
          <Body size={14}>{daily.target_elements?.includes(p.element) ? "우선 · " : "후보 · "}{p.label} {p.score}점</Body>
          <Muted size={12}>내 비율 {p.personal_percent}% · 개인 보완 {p.personal_points}/70 + 일진 관계 {p.day_points}/30</Muted>
          <Muted size={12}>{p.day_relation_label}</Muted>
        </View>)}
        <Muted size={12}>일진이 장소 오행을 생하면 30점, 같은 오행은 24점, 장소 오행이 일진을 생하면 18점, 장소→일진 상극은 6점, 일진→장소 상극은 0점으로 탐색 순서를 정해요.</Muted>
      </> : null}
    </Card>
    {data.catalog ? <>
      <Muted size={12}>장소의 소재와 오행 근거를 개인·일진 기준으로 비교한 결과예요. 기본 정합도와 오행 종합 점수는 별도로 표시하며, 운영시간은 장소 상세에서 확인할 수 있어요.</Muted>
      <Pressable accessibilityRole="link" onPress={() => { setLinkError(null); Linking.openURL(data.catalog!.license_url).catch(() => setLinkError("출처 링크를 열지 못했어요")); }}>
        <Muted size={12}>{data.catalog.label} · 이용 조건</Muted>
      </Pressable>
      {linkError ? <Muted size={12}>{linkError}</Muted> : null}
    </> : null}
    {data.items.length === 0 ? <Card style={{ gap: 8 }}>
      <Body>이 범위에서 우선 추천 오행이 확인된 장소를 찾지 못했어요.</Body>
      <Muted>기본 추천에서 지역이나 반경을 바꿔보세요. 오행을 확인할 수 없는 장소는 이 목록에 넣지 않아요.</Muted>
    </Card> : <Body>오행·일진 추가 추천 · {data.items.length}곳</Body>}
    {data.items.some((item) => item.discovery) ? <Muted size={12}>오행 종합 점수를 먼저 적용하고, 동점이면 사진·프로필 정합도·거리 등을 참고해요.</Muted> : null}
    {data.items.map((item) => <PlaceRecommendation key={item.recommendation_id} item={item} saju onPress={() => router.push({ pathname: "/place/[id]", params: {
      id: item.place_id, rec: String(item.recommendation_id), date, spot: item.spot_id, scene: item.scene_id, saju: "1",
    } })} />)}
  </>;
}
