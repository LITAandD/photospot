import type { PlaceDetail } from "@photospot/client";
import { googleMapUrl, naverMapUrl } from "@photospot/client";
import React, { useState } from "react";
import { Linking, Pressable, View } from "react-native";
import { Body, Button, Card, Muted } from "@/components/ui";

export function PlaceHours({ place }: { place: Pick<PlaceDetail, "hours" | "name" | "place_group"> }) {
  const [error, setError] = useState<string | null>(null);
  const { hours } = place;
  const travel = place.place_group === "travel";
  const label = travel ? "관람·운영시간" : "운영시간";
  const naver = naverMapUrl(null, hours?.source_url) ?? naverMapUrl(place.name);
  const google = googleMapUrl(place.name);
  const open = (url: string) => {
    setError(null);
    Linking.openURL(url).catch(() => setError("지도 정보를 열지 못했어요. 다시 시도해 주세요."));
  };
  return <View testID="place-hours"><Card style={{ gap: 8 }}>
    <Body>{label}{hours ? ` · ${hours.source_label}` : ""}</Body>
    {hours ? <>
      <Body size={14}>{hours.branch_name}</Body>
      <Body size={14}>{hours.schedule_kind === "source_text" ? "등록 안내" : "촬영일"} · {hours.summary}</Body>
      {hours.stale ? <Body size={14}>등록된 시간표를 다시 확인해 주세요.</Body> : null}
      {hours.weekly_hours.map((line) => <Body key={line} size={14}>{line}</Body>)}
      {hours.notes.map((line) => <Muted key={line} size={12}>{line}</Muted>)}
      <Pressable accessibilityRole="link" onPress={() => open(hours.source_url)}>
        <Muted size={12}>{hours.checked_at} {hours.provider === "openstreetmap" ? "수집" : "확인"} · 운영시간 출처 보기 ↗</Muted>
      </Pressable>
      <Muted size={12}>{hours.schedule_kind === "dated" ? "공식 안내에 게시된 날짜별 시간이에요. 임시 변경이 있을 수 있어요." : "등록된 운영시간이에요. 공휴일·임시휴무에 따라 달라질 수 있어요."}</Muted>
    </> : <>
      <Body size={14}>지도에서 운영시간을 확인해 주세요.</Body>
      <Muted size={12}>{travel ? "관람시간·휴관일·입장 마감을 확인해 주세요. 야외 명소도 구역별 출입 제한이 있을 수 있어요." : "영업시간·휴무일·마지막 입장 안내를 확인해 주세요."}</Muted>
    </>}
    {naver ? <Button title="네이버지도 운영시간 확인" variant="outline" onPress={() => open(naver)} /> : null}
    {google ? <Button title="구글지도 운영시간 확인" variant="outline" onPress={() => open(google)} /> : null}
    {error ? <Muted>{error}</Muted> : null}
  </Card></View>;
}
