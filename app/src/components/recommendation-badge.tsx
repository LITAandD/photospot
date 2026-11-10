import React from "react";
import { Text, View } from "react-native";
import { colors, fonts } from "@/theme";

const ELEMENTS: Record<string, string> = { wood: "목", fire: "화", earth: "토", metal: "금", water: "수" };

export function RecommendationBadge({ score, saju = false, elements = [] }: {
  score?: number | null; saju?: boolean; elements?: string[];
}) {
  const names = elements.map((e) => ELEMENTS[e]).filter(Boolean);
  const label = saju ? (names.length ? `${names.join("·")} 추천` : "오행 미확인")
    : typeof score === "number" && Number.isFinite(score) ? `정합도 ${Number(score.toFixed(1))}점` : "정합도 산정 전";
  return <View style={{ flexShrink: 0, maxWidth: 140, alignSelf: "flex-start", backgroundColor: colors.secondarySoft, borderRadius: 20, paddingHorizontal: 10, paddingVertical: 5 }}>
    <Text testID="recommendation-badge" style={{ fontFamily: fonts.semibold, fontSize: 12, lineHeight: 18, color: colors.secondaryInk }}>{label}</Text>
  </View>;
}
