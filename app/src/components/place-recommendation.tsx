import type { RecommendationItem } from "@photospot/client";
import React from "react";
import { Pressable, Text, View } from "react-native";
import { PlacePhoto } from "@/components/place-photo";
import { Muted } from "@/components/ui";
import { colors, fonts } from "@/theme";
import { RecommendationBadge } from "@/components/recommendation-badge";
import { DiscoverySummary } from "@/components/place-discovery";

export function PlaceRecommendation({ item, onPress, saju = false }: { item: RecommendationItem; onPress: () => void; saju?: boolean }) {
  return <Pressable testID="place-card" onPress={onPress} accessibilityRole="button"
    style={{ flexDirection: "row", gap: 12, padding: 12, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line }}>
    <PlacePhoto photo={item.cover_photo} placeholder={item.instagram_post_count ? "Instagram\n사진 보기 ↗" : undefined} fit="cover" style={{ width: 72, height: 72, aspectRatio: 1, flexShrink: 0, alignSelf: "flex-start", borderRadius: 12 }} label={item.place_name} />
    <View style={{ flex: 1, gap: 4 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
        <Text testID="place-name" style={{ fontFamily: fonts.semibold, fontSize: 15, color: colors.ink, flexShrink: 1 }}>{item.place_name}</Text>
        <RecommendationBadge score={item.scoring ? item.scoring.score : item.match_basis === "photo" && item.reasons.length ? item.score : item.fit_score} saju={saju} elements={item.recommended_elements} />
      </View>
      <View testID="place-kind"><Muted size={13}>{item.hours ? "" : `${item.time_slot_label} · `}{item.spot_name} · {(item.distance_m / 1000).toFixed(1)}km</Muted></View>
      {item.hours ? <View testID="hours-summary"><Muted size={12}>{item.hours.summary} · {item.hours.source_label}</Muted></View> : null}
      <DiscoverySummary evidence={item.discovery} />
      {item.instagram_post_count ? <Muted size={12}>Instagram 게시물 {item.instagram_post_count}개 · 상세에서 사진 보기</Muted> : null}
      {item.scoring ? <View testID="evaluation-coverage"><Muted size={12}>평가 {item.scoring.metrics.filter((m) => m.status === "scored").length}/{item.scoring.metrics.length}항목 · 가중치 {item.scoring.evaluated_weight ?? 0}/{item.scoring.total_weight} · 세부 지표 보기</Muted></View> : null}
      {saju && item.saju_match ? <View style={{ gap: 3 }}>
        <Muted size={13}>오행 종합 {item.saju_match.score}점 · {item.saju_match.label} 기준</Muted>
        <Muted size={12}>개인 보완 {item.saju_match.personal_points} + 일진 관계 {item.saju_match.day_points}</Muted>
      </View> : null}
      {!saju && item.scoring ? <View testID="score-summary"><Muted size={12}>{item.scoring.metrics.filter((m) => m.points != null).map((m) => `${m.label} ${m.points}점`).join(" · ") || (item.scoring.metrics.some((m) => m.status === "pending") ? "사진·공간 특징을 확인한 뒤 점수를 제공해요" : "프로필을 입력하면 점수를 볼 수 있어요")}</Muted>
      </View> : null}
      <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.accentInk }}>{item.reasons.map((r) => r.label).join(" · ")}</Text>
      {saju && item.element_profile ? <Muted size={12}>{item.element_profile.label} · 상세에서 지정 근거 보기</Muted> : null}
      {item.cover_photo ? <Muted size={10}>{item.cover_photo.attribution} · {item.cover_photo.license}</Muted> : null}
    </View>
  </Pressable>;
}
