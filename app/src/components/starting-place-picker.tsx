import React, { useState } from "react";
import { Linking, Pressable, StyleSheet, View } from "react-native";
import { Body, Button, Card, Chip, Muted } from "./ui";
import { POLICY_URLS } from "@/policy-links";
import { track } from "@/analytics";
import { RECOMMENDATION_REGIONS, SUPPORTED_REGIONS, type StartingPlace } from "@/recommendation-regions";
import type { StartingPlaceState } from "@/starting-place";
import { colors } from "@/theme";

/**
 * 시작 장소 선택. 현위치는 자동으로 조회하지 않고 '내 주변에서 찾기' → 위치정보 이용 동의 → 기기 권한 순서로만 요청한다.
 * 동의 전에는 onLocate를 부르지 않으므로 좌표가 서버로 가지 않는다.
 */
export function StartingPlacePicker({ state, consented, onConsent, onLocate, onSelect, onOpenTerms }: {
  state: StartingPlaceState; consented: boolean; onConsent: () => void; onLocate: () => void; onSelect: (place: StartingPlace) => void;
  /** 위치정보 이용약관 열기. 기본은 EXPO_PUBLIC_LOCATION_TERMS_URL */
  onOpenTerms?: () => void;
}) {
  const [city, setCity] = useState("서울");
  const [expanded, setExpanded] = useState(false);
  const [asking, setAsking] = useState(false);
  const [termsError, setTermsError] = useState(false);
  const region = RECOMMENDATION_REGIONS.find((item) => item.name === city)!;
  const showRegions = expanded || !state.place;
  const nearby = () => { if (consented) onLocate(); else setAsking(true); };
  // 동의 기록 직후·위치 조회 전에 이벤트만 남긴다(좌표는 보내지 않음).
  const agree = () => { setAsking(false); onConsent(); void track("gps_allow"); onLocate(); };
  const openTerms = () => {
    if (onOpenTerms) return onOpenTerms();
    if (!POLICY_URLS.location) return setTermsError(true);
    Linking.openURL(POLICY_URLS.location).catch(() => setTermsError(true));
  };
  return <Card style={{ gap: 12 }}>
    <Body>추천 시작 장소</Body>
    <Muted size={13}>{state.locating ? "현위치를 확인하고 있어요. 기다리는 동안 지역을 골라도 좋아요."
      : state.place ? `${state.place.label}에서 가까운 사진 장소를 찾아요.` : `어디서 출발할까요? 도시와 주요 장소를 골라 주세요. 지금은 ${SUPPORTED_REGIONS} 지역을 추천해요.`}</Muted>
    {asking ? <View style={s.sheet} accessibilityViewIsModal accessibilityLabel="위치정보 이용 동의">
      <Body>위치정보 이용 동의</Body>
      <Muted size={13}>내 주변 장소를 찾기 위해 현재 위치(좌표)를 한 번 확인해 추천 서버로 보내요. 좌표는 추천 계산에만 쓰고 저장하지 않으며, 위치를 계속 추적하지 않아요. 동의하면 기기의 위치 권한을 요청해요.</Muted>
      <Pressable accessibilityRole="link" onPress={openTerms} style={{ minHeight: 44, justifyContent: "center" }}><Body size={14}>위치정보 이용약관 보기 ›</Body></Pressable>
      {termsError ? <Muted size={12}>약관 문서를 열지 못했어요. 개인정보 및 서비스 안내 화면에서 다시 확인해 주세요.</Muted> : null}
      <Button title="동의하고 내 주변에서 찾기" onPress={agree} />
      <Button title="다음에 할게요" variant="outline" onPress={() => setAsking(false)} />
    </View> : <Button title={state.place?.id === "current" ? "내 주변 다시 확인" : "내 주변에서 찾기"} onPress={nearby} loading={state.locating} variant={state.place?.id === "current" ? "primary" : "outline"} />}
    {state.note ? <Muted size={13}>{state.note}</Muted> : null}
    {state.place ? <Button title={expanded ? "지역 선택 닫기" : "도시·주요 장소에서 선택"} onPress={() => setExpanded(!expanded)} variant="outline" /> : null}
    {showRegions ? <>
      <View style={s.row}>
        {RECOMMENDATION_REGIONS.map((item) => <Chip key={item.name} label={`${item.name} ${item.areas.length}곳`} selected={city === item.name} onPress={() => setCity(item.name)} role="radio" />)}
      </View>
      <View style={s.row}>
        {region.areas.map((area) => <Pressable key={area.id} accessibilityRole="button" accessibilityLabel={`${area.label}에서 시작`} accessibilityState={{ selected: state.place?.id === area.id }}
          style={[s.area, state.place?.id === area.id && s.selected]}
          onPress={() => { onSelect(area); setExpanded(false); }}>
          <Body size={14}>{area.name}</Body>
          <Muted size={11}>{area.description}</Muted>
        </Pressable>)}
      </View>
      <Muted size={11}>선택한 장소를 중심으로 주변을 검색해요. 촬영일·거리·시간에서 검색 반경을 조절할 수 있어요.</Muted>
    </> : null}
  </Card>;
}

const s = StyleSheet.create({
  row: { flexDirection: "row", flexWrap: "wrap", gap: 8 },
  sheet: { gap: 10, padding: 14, borderWidth: 1, borderColor: colors.accent, borderRadius: 12, backgroundColor: colors.accentSoft },
  area: { flexGrow: 1, flexBasis: "46%", minWidth: 125, padding: 12, gap: 4, borderWidth: 1, borderColor: colors.line, borderRadius: 12, backgroundColor: colors.card },
  selected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
});
