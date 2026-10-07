import React, { useState } from "react";
import { Pressable, StyleSheet, View } from "react-native";
import { Body, Button, Card, Chip, Muted } from "./ui";
import { RECOMMENDATION_REGIONS, type StartingPlace } from "@/recommendation-regions";
import type { StartingPlaceState } from "@/starting-place";
import { colors } from "@/theme";

export function StartingPlacePicker({ state, onLocate, onSelect }: {
  state: StartingPlaceState; onLocate: () => void; onSelect: (place: StartingPlace) => void;
}) {
  const [city, setCity] = useState("서울");
  const [expanded, setExpanded] = useState(false);
  const region = RECOMMENDATION_REGIONS.find((item) => item.name === city)!;
  const showRegions = expanded || !state.place;
  return <Card style={{ gap: 12 }}>
    <Body>추천 시작 장소</Body>
    <Muted size={13}>{state.locating ? "현위치를 확인하고 있어요. 기다리는 동안 지역을 골라도 좋아요."
      : state.place ? `${state.place.label}에서 가까운 사진 장소를 찾아요.` : "어디서 출발할까요? 도시와 주요 장소를 골라 주세요."}</Muted>
    <Button title={state.place?.id === "current" ? "현위치 다시 확인" : "현위치에서 시작"} onPress={onLocate} loading={state.locating} variant={state.place?.id === "current" ? "primary" : "outline"} />
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
  area: { flexGrow: 1, flexBasis: "46%", minWidth: 125, padding: 12, gap: 4, borderWidth: 1, borderColor: colors.line, borderRadius: 12, backgroundColor: colors.card },
  selected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
});
