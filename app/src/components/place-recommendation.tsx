import type { RecommendationItem } from "@photospot/client";
import React from "react";
import { recommendationSummary } from "@/recommendation-summary";
import { Pressable, Text, View, useWindowDimensions } from "react-native";
import { PlacePhoto } from "@/components/place-photo";
import { colors, fonts } from "@/theme";
import { RecommendationBadge } from "@/components/recommendation-badge";

export function PlaceRecommendation({ item, onPress }: { item: RecommendationItem; onPress: () => void }) {
  const summary = recommendationSummary(item);
  const closed = item.hours?.closed === true;   // 촬영일이 확인된 휴무일(서버 PlaceHours.closed)
  const thumb = useWindowDimensions().width < 360 ? 92 : 112;
  return <Pressable testID="place-card" onPress={onPress} accessibilityRole="button"
    style={({pressed}) => [{ flexDirection: "row", gap: 14, padding: 10, borderRadius: 22, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line }, pressed && { backgroundColor: colors.accentSoft }]}>
    <PlacePhoto photo={item.cover_photo} fit="cover" style={{ width: thumb, height: thumb, aspectRatio: 1, flexShrink: 0, alignSelf: "flex-start", borderRadius: 16 }} label={item.place_name} />
    <View style={{ flex: 1, minWidth: 0, minHeight: thumb, paddingVertical: 4, gap: 8, justifyContent: 'center' }}>
      <Text testID="place-name" numberOfLines={2} style={{ fontFamily: fonts.semibold, fontSize: 16, lineHeight: 23, letterSpacing: -0.4, color: colors.ink }}>{item.place_name}</Text>
      {closed ? <View testID="hours-closed" style={{ alignSelf: "flex-start", borderRadius: 6, paddingHorizontal: 6, paddingVertical: 2, backgroundColor: "#F7E6DF" }}>
        <Text style={{ fontFamily: fonts.semibold, fontSize: 11, lineHeight: 15, color: colors.terracotta }}>선택일 휴무</Text>
      </View> : null}
      <Text testID="recommendation-reason" numberOfLines={2} style={{ fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.ink }}>{summary.reason}</Text>
      <Text testID="recommendation-evidence" style={{ fontFamily: fonts.body, fontSize: 10, lineHeight: 15, color: colors.muted }}>{summary.evidence}</Text>
      {item.hours ? <Text testID="hours-summary" numberOfLines={2} style={{ fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.muted }}>
        운영시간 · {item.hours.summary}
      </Text> : null}
      <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <RecommendationBadge score={item.scoring ? item.scoring.score : item.match_basis === "photo" && item.reasons.length ? item.score : item.fit_score} />
        <Text testID="place-distance" style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>{(item.distance_m / 1000).toFixed(1)}km</Text>
      </View>
    </View>
  </Pressable>;
}
