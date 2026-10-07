import type { RecommendationItem } from "@photospot/client";
import React, { useState } from "react";
import { Linking, Pressable, View } from "react-native";
import { Body, Card, Muted } from "@/components/ui";

type Evidence = NonNullable<RecommendationItem["discovery"]>;

function signalText(signal: NonNullable<Evidence["popularity"]>[number]) {
  return `${signal.label} ${signal.value.toLocaleString("ko-KR")}${signal.metric === "naver_local_rank" ? "위" : "건"}`;
}

export function DiscoverySummary({ evidence }: { evidence?: Evidence | null }) {
  if (!evidence) return null;
  const parts = [evidence.photo_count > 0 ? `사진 ${evidence.photo_count}장` : null,
    ...(evidence.popularity ?? []).map(signalText)].filter(Boolean);
  return parts.length ? <View testID="discovery-summary"><Muted size={12}>{parts.join(" · ")}</Muted></View> : null;
}

export function DiscoveryDetails({ evidence }: { evidence?: Evidence | null }) {
  const [error, setError] = useState<string | null>(null);
  if (!evidence?.popularity?.length) return null;
  return <View testID="discovery-details"><Card style={{ gap: 10 }}>
    <Body>리뷰·게시물 참고</Body>
    {evidence.popularity.map((signal) => <View key={signal.metric} style={{ gap: 4 }}>
      <Body size={14}>{signalText(signal)}</Body>
      <Muted size={12}>{signal.scope}</Muted>
      <Pressable accessibilityRole="link" onPress={() => Linking.openURL(signal.source_url).catch(() => setError("출처를 열지 못했어요"))}>
        <Muted size={12}>{signal.checked_at} 확인 · 출처 보기 ↗</Muted>
      </Pressable>
    </View>)}
    <Muted size={12}>확인 시점의 공개 집계예요. 방문자·블로그 리뷰가 포함될 수 있으며, 현재 수치와 다를 수 있어요. 추천 순서에 참고하고 정합도 점수에는 더하지 않아요.</Muted>
    {error ? <Muted>{error}</Muted> : null}
  </Card></View>;
}
