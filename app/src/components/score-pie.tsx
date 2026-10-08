import React from "react";
import { Text, View } from "react-native";
import Svg, { Circle, Path } from "react-native-svg";
import { colors, fonts } from "@/theme";

/** Use the final score, after deductions, so the pie always matches the badge. */
export function ScorePie({ score }: { score?: number | null }) {
  const value = typeof score === "number" && Number.isFinite(score) ? Math.max(0, Math.min(100, score)) : null;
  const display = value == null ? "산정 전" : `${Number(value.toFixed(1))}`;
  const angle = (value ?? 0) / 100 * Math.PI * 2 - Math.PI / 2;
  const x = 90 + 82 * Math.cos(angle), y = 90 + 82 * Math.sin(angle);
  return <View testID="score-pie-summary" style={{ flexDirection: "row", flexWrap: "wrap", alignItems: "center", justifyContent: "center", gap: 22 }}>
    <View testID="score-pie" accessible accessibilityRole="image"
      accessibilityLabel={value == null ? "정합도 산정 전. 평가된 항목이 없어요." : `전체 정합도 ${display}점, 100점 중 ${display}점 획득. 미획득·미평가 ${Number((100 - value).toFixed(1))}점.`}>
      <Svg width={180} height={180} viewBox="0 0 180 180" aria-hidden>
        <Circle cx={90} cy={90} r={82} fill={colors.line} />
        {value === 100 ? <Circle cx={90} cy={90} r={82} fill={colors.accent} /> : value != null && value > 0 ?
          <Path d={`M 90 90 L 90 8 A 82 82 0 ${value > 50 ? 1 : 0} 1 ${x} ${y} Z`} fill={colors.accent} /> : null}
      </Svg>
    </View>
    <View style={{ gap: 12, minWidth: 130 }}>
      <View style={{ flexDirection: "row", alignItems: "baseline", gap: 5 }}>
        <Text testID="score-total" style={{ color: colors.ink, fontFamily: fonts.semibold, fontSize: value == null ? 28 : 38 }}>{display}</Text>
        {value != null ? <Text style={{ color: colors.muted, fontFamily: fonts.body, fontSize: 14 }}>/ 100점</Text> : null}
      </View>
      <Legend color={colors.accent} label={value == null ? "획득 점수 확인 전" : `획득 ${display}점`} />
      <Legend color={colors.line} label={value == null ? "미평가·미입력" : `미획득·미평가 ${Number((100 - value).toFixed(1))}점`} />
    </View>
  </View>;
}

function Legend({ color, label }: { color: string; label: string }) {
  return <View style={{ flexDirection: "row", alignItems: "center", gap: 7 }}>
    <View style={{ width: 10, height: 10, borderRadius: 3, backgroundColor: color }} />
    <Text style={{ color: colors.muted, fontFamily: fonts.body, fontSize: 12 }}>{label}</Text>
  </View>;
}
