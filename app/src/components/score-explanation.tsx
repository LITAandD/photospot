import type { ScoreExplanation, ScoreWeight } from "@photospot/client";
import React, { useState } from "react";
import { Linking, Pressable, Text, View } from "react-native";
import { Body, Card, Label, Muted } from "@/components/ui";
import { colors, fonts } from "@/theme";

const number = (value: number) => Number(value.toFixed(1)).toString();
const STATUS = { pending: "미평가", missing_input: "미입력", optional: "미적용", scored: "" };

export function ScoreDetails({ scoring }: { scoring?: ScoreExplanation | null }) {
  if (!scoring) return null;
  const earned = scoring.metrics.reduce((sum, metric) => sum + (metric.points ?? 0), 0);
  const evaluated = scoring.metrics.filter((metric) => metric.status === "scored").length;
  return <Card style={{ gap: 14 }}>
    <View testID="score-details" style={{ gap: 14 }}>
      <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 8 }}>
        <Label>전체 지표 정합도</Label>
        <Body>{scoring.score == null ? "산정 전" : `${number(scoring.score)} / 100점`}</Body>
      </View>
      {scoring.score != null && scoring.total_weight != null ? <View testID="score-total" style={{ gap: 8 }}>
        <Body size={13}>획득 배점 {number(earned)} / {number(scoring.total_weight)}점 · 전체 배점 기준</Body>
        <View style={{ height: 7, backgroundColor: colors.line, borderRadius: 4 }}>
          <View style={{ height: 7, borderRadius: 4, width: `${Math.max(0, Math.min(100, scoring.score))}%`, backgroundColor: colors.accent }} />
        </View>
      </View> : null}
      <Muted size={12}>{scoring.basis === "category" ? "공간·설명·방문객 정합도" : "사진·공간·방문객 정합도"}</Muted>
      {scoring.evaluated_weight != null ? <Muted size={12}>평가 완료 {evaluated}/{scoring.metrics.length}항목 · 확인된 배점 {scoring.evaluated_weight}/{scoring.total_weight} · {scoring.evidence_method || "항목별 근거는 아래에서 확인해 주세요"}</Muted> : null}
      {scoring.metrics.map((metric) => <View key={metric.key} testID={`score-metric-${metric.key}`} style={{ gap: 4 }}>
        <View style={{ flexDirection: "row", justifyContent: "space-between", gap: 8 }}>
          <Body size={13}>{metric.label}</Body>
          <Body size={13}>{metric.points == null ? STATUS[metric.status] : `${number(metric.points)} / ${number(metric.maximum ?? metric.weight)}점`}</Body>
        </View>
        {metric.points != null && metric.maximum != null && metric.maximum > 0 ? <View style={{ height: 5, backgroundColor: colors.line, borderRadius: 3 }}>
          <View style={{ height: 5, borderRadius: 3, width: `${Math.min(100, 100 * Math.abs(metric.points) / metric.maximum)}%`, backgroundColor: metric.points < 0 ? colors.terracotta : colors.accent }} />
        </View> : null}
        {metric.note ? <Muted size={11}>{metric.note}</Muted> : null}
        {(metric.sources ?? []).map((source) => <View key={source.url} style={{ gap: 3 }}>
          {source.excerpt ? <Muted size={11}>“{source.excerpt}”</Muted> : null}
          <Pressable accessibilityRole="link" onPress={() => Linking.openURL(source.url)}>
            <Text style={{ color: colors.accentInk, fontSize: 11 }}>{source.label}{source.checked_at ? ` · ${source.checked_at} 확인` : ""} ↗</Text>
          </Pressable>
        </View>)}
      </View>)}
      <Muted size={12}>{scoring.note}</Muted>
      {scoring.visitor_context ? <View testID="visitor-coverage" style={{ gap: 5 }}>
        <Body size={13}>방문객 통계 · {scoring.visitor_context.period_start}~{scoring.visitor_context.period_end}</Body>
        <Body size={13}>{scoring.visitor_context.visitors == null ? "연간 입장객 미집계" : `${scoring.visitor_context.visitors.toLocaleString()}명 · 집계 장소 중 ${scoring.visitor_context.rank}위`}</Body>
        {scoring.visitor_context.unit_label ? <Muted size={11}>통계 집계 단위: {scoring.visitor_context.unit_label}</Muted> : null}
        <Muted size={12}>전체 DB {scoring.visitor_context.catalog_count.toLocaleString()}곳 중 동일 기간 집계 {scoring.visitor_context.measured_count.toLocaleString()}곳 · {scoring.visitor_context.as_of} 기준</Muted>
        <Muted size={11}>2025년 연간 입장객 수를 비교해요. 실시간 혼잡도는 아니며, 규모·운영일수의 영향이 있어요. 미집계 장소는 순위에서 제외하고, 중복 장소는 대표 지점 하나만 집계해요.</Muted>
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
      <Muted size={12}>획득 배점의 합계를 전체 기본 배점 {number(weights.filter((w) => !w.optional).reduce((sum, w) => sum + w.weight, 0))}점 기준으로 100점 환산해요. 미평가·미입력 항목도 전체 배점에 포함하며 확인 전에는 점수를 더하지 않아요. 오행·일진은 별도로 평가해요.</Muted>
      <Pressable accessibilityRole="button" accessibilityState={{ expanded }} onPress={() => setExpanded(!expanded)}>
        <Text style={{ fontFamily: fonts.semibold, fontSize: 13, color: colors.accentInk }}>{expanded ? "세부 가중치 접기" : "세부 가중치 보기"}</Text>
      </Pressable>
      {expanded ? <Muted size={12}>체형: 곡선→웨이브 · 직선→내추럴 · 큰 형체→스트레이트. 사진 색조: 난색→웜톤 · 한색→쿨톤. 키는 배점에 반영하지 않아요.</Muted> : null}
      {expanded ? <Muted size={12}>E/I: 2025년 입장객 순위에서 많은 곳/적은 곳을 각각 선호해요. S/N: 네이버지도·인스타그램의 공간 설명에서 디테일·섬세·정교·세밀 / 컨셉·콘셉트·테마·세계관 문구를 확인해요. T/F: 건축물 / 자연물 중심 공간을 비교해요. 두 성격이 함께 확인되면 중립으로 평가해요.</Muted> : null}
      {expanded ? <Muted size={12}>J/P 검토안: 일정 확정 가능성 / 방문 자유도. 예약 조건·운영시간·자유 관람 근거를 갖춘 뒤 도입할 항목으로, 현재 점수에는 포함하지 않아요.</Muted> : null}
      {expanded ? weights.map((w) => <View key={w.key} style={{ gap: 3 }}>
        <Body size={13}>{w.label} · 가중치 {number(w.weight)}</Body>
        <Muted size={12}>{w.detail}</Muted>
      </View>) : null}
    </View>
  </Card>;
}
