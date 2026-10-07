import type { ScoreExplanation, ScoreWeight } from "@photospot/client";
import React, { useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";
import { Body, Card, Label, Muted } from "@/components/ui";
import { colors, fonts } from "@/theme";

const number = (value: number) => Number(value.toFixed(1)).toString();
const STATUS = { pending: "미평가", missing_input: "미입력", optional: "미적용", scored: "" };

export function ScoreDetails({ scoring }: { scoring?: ScoreExplanation | null }) {
  if (!scoring) return null;
  return <Card style={{ gap: 14 }}>
    <View testID="score-details" style={{ gap: 14 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <Label>정합도 지표</Label>
        <Body>{scoring.score == null ? "산정 전" : `${number(scoring.score)} / 100점`}</Body>
      </View>
      <Muted size={12}>{scoring.basis === "category" ? "장소 유형 정합도" : "사진·공간·방문객 정합도"}</Muted>
      {scoring.evaluated_weight != null ? <Muted size={12}>평가 범위: 전체 가중치 {scoring.total_weight} 중 {scoring.evaluated_weight} · {scoring.evidence_method || "자료 확인 전"}</Muted> : null}
      {scoring.metrics.map((metric) => <View key={metric.key} testID={`score-metric-${metric.key}`} style={{ gap: 4 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
          <Body size={13}>{metric.label}</Body>
          <Body size={13}>{metric.points == null ? STATUS[metric.status] : `${number(metric.points)} / ${number(metric.maximum ?? metric.weight)}점`}</Body>
        </View>
        {metric.points != null && metric.maximum != null && metric.maximum > 0 ? <View style={{ height: 5, backgroundColor: colors.line, borderRadius: 3 }}>
          <View style={{ height: 5, borderRadius: 3, width: `${Math.min(100, 100 * Math.abs(metric.points) / metric.maximum)}%`, backgroundColor: metric.points < 0 ? colors.terracotta : colors.accent }} />
        </View> : null}
        {metric.note ? <Muted size={11}>{metric.note}</Muted> : null}
      </View>)}
      <Muted size={12}>{scoring.note}</Muted>
      {scoring.visitor_context ? <View testID="visitor-coverage" style={{ gap: 5 }}>
        <Body size={13}>방문객 통계 · {scoring.visitor_context.period_start}~{scoring.visitor_context.period_end}</Body>
        <Muted size={12}>전체 DB {scoring.visitor_context.catalog_count.toLocaleString()}곳 중 동일 기간 집계 {scoring.visitor_context.measured_count.toLocaleString()}곳 · {scoring.visitor_context.as_of} 기준</Muted>
        <Muted size={11}>공개된 장소별 월간 입장객 수를 합산해 비교해요. 미집계 장소는 순위에서 제외하며, 방문객 수가 0명인 것으로 처리하지 않아요.</Muted>
        {(scoring.visitor_context.sources ?? []).map((source) => <Pressable key={source.url} accessibilityRole="link" onPress={() => Linking.openURL(source.url)}>
          <Text style={{ color: colors.accentInk }}>{source.label} · 방문객 통계 원문 ↗</Text>
        </Pressable>)}
      </View> : null}
      {scoring.evidence_url ? <Pressable accessibilityRole="link" onPress={() => Linking.openURL(scoring.evidence_url!)}><Text style={{ color: colors.accentInk }}>평가에 사용한 사진 보기 ↗</Text></Pressable> : null}
    </View>
  </Card>;
}

export function ScoringGuide({ weights }: { weights?: ScoreWeight[] }) {
  const [expanded, setExpanded] = useState(false);
  if (!weights?.length) return null;
  return <Card style={{ gap: 10 }}>
    <View testID="scoring-guide" style={{ gap: 10 }}>
      <Label>정합도 판단 기준</Label>
      <Body size={13}>{weights.filter((w) => !w.optional).map((w) => `${w.label} ${number(w.weight)}`).join(" · ")}</Body>
      <Muted size={12}>확인 가능한 사진·공간·방문객 항목으로 100점 환산해요. 미평가 항목은 제외하고, 오행·일진은 추가 장소 선택에 별도로 반영해요.</Muted>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(!expanded)}>
        <Text style={{ fontFamily: fonts.semibold, fontSize: 13, color: colors.accentInk }}>{expanded ? "세부 가중치 접기" : "세부 가중치 보기"}</Text>
      </Pressable>
      {expanded ? <Muted size={12}>체형: 곡선→웨이브 · 직선→내추럴 · 큰 형체→스트레이트. 키: 170cm 초과→야외 · 미만→실내 · 170cm→중립. 사진 색조: 난색→웜톤 · 한색→쿨톤. MBTI E/I: 최근 3개월 방문객 수가 많은/적은 장소를 각각 선호해요.</Muted> : null}
      {expanded ? weights.map((w) => <View key={w.key} style={{ gap: 3 }}>
        <Body size={13}>{w.label} · 가중치 {number(w.weight)}</Body>
        <Muted size={12}>{w.detail}</Muted>
      </View>) : null}
    </View>
  </Card>;
}
