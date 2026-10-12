import type { RecommendationItem } from "@photospot/client";
import React from "react";
import { Pressable, Text, View } from "react-native";
import { PlacePhoto } from "@/components/place-photo";
import { colors, fonts } from "@/theme";
import { RecommendationBadge } from "@/components/recommendation-badge";

export function PlaceRecommendation({ item, onPress }: { item: RecommendationItem; onPress: () => void }) {
  return <Pressable testID="place-card" onPress={onPress} accessibilityRole="button"
    style={{ flexDirection: "row", gap: 12, padding: 12, borderRadius: 16, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line }}>
    <PlacePhoto photo={item.cover_photo} fit="cover" style={{ width: 72, height: 72, aspectRatio: 1, flexShrink: 0, alignSelf: "flex-start", borderRadius: 12 }} label={item.place_name} />
    <View style={{ flex: 1, minWidth: 0, minHeight: 72, gap: 6 }}>
      <Text testID="place-name" numberOfLines={2} style={{ fontFamily: fonts.semibold, fontSize: 15, lineHeight: 21, color: colors.ink }}>{item.place_name}</Text>
      <Text testID="hours-summary" numberOfLines={2} style={{ fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.muted }}>
        운영시간 · {item.hours?.summary ?? "미확인"}
      </Text>
      <View style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "space-between", gap: 8 }}>
        <RecommendationBadge score={item.scoring ? item.scoring.score : item.match_basis === "photo" && item.reasons.length ? item.score : item.fit_score} />
        <Text testID="place-distance" style={{ fontFamily: fonts.body, fontSize: 12, color: colors.muted }}>{(item.distance_m / 1000).toFixed(1)}km</Text>
      </View>
    </View>
  </Pressable>;
}
