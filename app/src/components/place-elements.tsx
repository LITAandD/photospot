import type { PlaceDetail } from "@photospot/client";
import React, { useState } from "react";
import { Linking, Pressable, View } from "react-native";
import { Body, Card, Label, Muted } from "@/components/ui";

const BASIS = { traditional: "전통 문헌", regional: "지역 지형 해석", landscape: "경관·소재 해석", unassigned: "근거 확인 전" };

export function PlaceElements({ profile }: { profile: PlaceDetail["element_profile"] }) {
  const [failed, setFailed] = useState(false);
  if (!profile) return null;
  return <View testID="place-elements"><Card style={{ gap: 10 }}>
    <Label>이 장소의 오행</Label>
    <Body>{profile.label}</Body>
    <Muted size={12}>{BASIS[profile.basis]}</Muted>
    <Body size={13}>{profile.explanation}</Body>
    {profile.sources.length ? <View style={{ gap: 8 }}>
      <Label>지정 근거</Label>
      {profile.sources.map((source) => <Pressable key={source.url} accessibilityRole="link" onPress={() => {
        setFailed(false); Linking.openURL(source.url).catch(() => setFailed(true));
      }}><Body size={12}>{source.title} ↗</Body></Pressable>)}
    </View> : null}
    {failed ? <Muted>출처를 열지 못했어요. 다시 시도해 주세요.</Muted> : null}
    {profile.elements.length ? <Muted size={11}>전통 상징과 지형을 참고한 추천 기준이에요. 해석 방식에 따라 달라질 수 있어요.</Muted> : null}
  </Card></View>;
}
