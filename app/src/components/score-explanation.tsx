import type { ScoreExplanation, ScoreWeight } from "@photospot/client";
import React from "react";
import { Linking, Pressable, Text, View } from "react-native";
import { Body, Card, Label, Muted } from "@/components/ui";
import { colors } from "@/theme";
import { ScorePie } from "@/components/score-pie";
import { ScoreDisclosure } from "@/components/score-disclosure";

const number = (value: number) => Number(value.toFixed(1)).toString();
const STATUS = { pending: "미평가", missing_input: "미입력", optional: "미적용", scored: "" };

export function ScoreDetails({ scoring }: { scoring?: ScoreExplanation | null }) {
  if (!scoring) return null;
  const earned = scoring.metrics.reduce((sum, metric) => sum + (metric.points ?? 0), 0);
  const evaluated = scoring.metrics.filter((metric) => metric.status === "scored").length;
  return <Card style={{ gap: 14 }}>
    <View testID="score-details" style={{ gap: 14 }}>
      <Label>전체 지표 정합도</Label>
      <ScorePie score={scoring.score} />
      <Muted size={12}>평가 완료 {evaluated}/{scoring.metrics.length}항목 · 미평가는 부적합 판정이 아니에요.</Muted>
      {scoring.evidence_ready_count != null ? <View testID="score-evidence-coverage"><Muted size={12}>근거 확보 {scoring.evidence_ready_count}/7항목 · 프로필 입력 여부와 별개이며, 지도 분류 추정을 포함해요.</Muted></View> : null}
      {scoring.evidence_photo_id ? <Muted size={12}>
        {scoring.photo_selection === 'likes' ? '좋아요 1위 대표사진' : '현재 대표사진'}을 사진 지표의 근거로 사용해요.
        {scoring.photo_analysis_pending ? ' 아직 분석하지 못한 사진 항목은 미평가로 표시해요.' : ' 좋아요 수 자체는 정합도 점수에 더하지 않아요.'}
      </Muted> : null}
      <Muted size={12}>지표를 누르면 평가 근거와 출처를 펼쳐볼 수 있어요.</Muted>
      <View>
      {scoring.metrics.map((metric) => <View key={metric.key} style={{ borderTopWidth: 1, borderTopColor: colors.divider }}>
        <ScoreDisclosure testID={`score-metric-${metric.key}`} title={metric.label}
          summary={metric.points == null ? STATUS[metric.status] : metric.points < 0 ? `${number(-metric.points)}점 감점` : `${number(metric.points)} / ${number(metric.maximum ?? metric.weight)}점`}>
        {metric.points != null && metric.points < 0 ? <Muted size={12}>프로필과 반대되는 특징으로 총점에서 {number(-metric.points)}점을 차감했어요. 이 항목의 최대 가점은 {number(metric.maximum ?? metric.weight)}점이에요.</Muted> : null}
        {metric.points != null && metric.maximum != null && metric.maximum > 0 ? <View style={{ height: 5, backgroundColor: colors.line, borderRadius: 3 }}>
          <View style={{ height: 5, borderRadius: 3, width: `${Math.min(100, 100 * Math.abs(metric.points) / metric.maximum)}%`, backgroundColor: metric.points < 0 ? colors.terracotta : colors.accent }} />
        </View> : null}
        {metric.note ? <Muted size={11}>{metric.note}</Muted> : null}
        {metric.status === 'missing_input' && metric.evidence_status === 'ready' ? <Muted size={11}>이 장소의 근거는 있어요. 해당 프로필을 입력하면 비교할 수 있어요.</Muted> : null}
        {(metric.sources ?? []).map((source) => <View key={source.url} style={{ gap: 3 }}>
          {source.excerpt ? <Muted size={11}>“{source.excerpt}”</Muted> : null}
          <Pressable accessibilityRole="link" onPress={() => Linking.openURL(source.url)}>
            <Text style={{ color: colors.accentInk, fontSize: 11 }}>{source.label}{source.checked_at ? ` · ${source.checked_at} 확인` : ""} ↗</Text>
          </Pressable>
        </View>)}
        {metric.key === "mbti_ei.crowd_level" && scoring.visitor_context ? <VisitorCoverage context={scoring.visitor_context} /> : null}
        </ScoreDisclosure>
      </View>)}
      <View style={{ borderTopWidth: 1, borderTopColor: colors.divider }}>
        <ScoreDisclosure title="점수 계산과 평가 범위" testID="score-method">
          <Muted size={12}>{scoring.basis === "category" ? "공간·설명·방문객 정합도" : "사진·공간·방문객 정합도"}</Muted>
          {scoring.total_weight != null ? <Body size={13}>감점 포함 배점 합계 {number(earned)} / {number(scoring.total_weight)}점 · 평가한 배점 {scoring.evaluated_weight ?? 0}/{scoring.total_weight}</Body> : null}
          {scoring.preference_score != null ? <View testID="score-preference-fit"><Muted size={12}>평가한 항목 내 취향 일치도 {number(scoring.preference_score)}% · 미평가 항목을 뺀 참고값으로, 전체 정합도나 추천 순서와는 달라요.</Muted></View> : null}
          <Muted size={12}>{scoring.note}</Muted>
          {scoring.evidence_method ? <Muted size={11}>{scoring.evidence_method}</Muted> : null}
          {scoring.evidence_url ? <Pressable accessibilityRole="link" onPress={() => Linking.openURL(scoring.evidence_url!)}><Text style={{ color: colors.accentInk }}>평가에 사용한 사진 보기 ↗</Text></Pressable> : null}
        </ScoreDisclosure>
      </View>
      </View>
    </View>
  </Card>;
}

function VisitorCoverage({ context }: { context: NonNullable<ScoreExplanation["visitor_context"]> }) {
  return <View testID="visitor-coverage" style={{ gap: 5 }}>
        <Body size={13}>방문객 통계 · {context.period_start}~{context.period_end}</Body>
        <Body size={13}>{context.visitors == null ? "연간 입장객 미집계" : `${context.visitors.toLocaleString()}명 · 집계 장소 중 ${context.rank}위`}</Body>
        {context.unit_label ? <Muted size={11}>통계 집계 단위: {context.unit_label}</Muted> : null}
        <Muted size={12}>전체 DB {context.catalog_count.toLocaleString()}곳 중 동일 기간 집계 {context.measured_count.toLocaleString()}곳 · {context.as_of} 기준</Muted>
        <Muted size={11}>2025년 연간 입장객 수를 비교해요. 실시간 혼잡도는 아니며, 규모·운영일수의 영향이 있어요. 미집계 장소는 순위에서 제외하고, 중복 장소는 대표 지점 하나만 집계해요.</Muted>
        {(context.sources ?? []).map((source) => <Pressable key={source.url} accessibilityRole="link" onPress={() => Linking.openURL(source.url)}>
          <Text style={{ color: colors.accentInk }}>{source.label} · 방문객 통계 원문 ↗</Text>
        </Pressable>)}
      </View>;
}

export function ScoringGuide({ weights, compact = false }: { weights?: ScoreWeight[]; compact?: boolean }) {
  if (!weights?.length) return null;
  return <Card style={{ gap: 10, ...(compact ? { paddingVertical: 2, borderWidth: 0, backgroundColor: 'transparent' } : {}) }}>
    <ScoreDisclosure testID="scoring-guide" title="정합도 판단 기준">
      <Body size={13}>{weights.filter((w) => !w.optional).map((w) => `${w.label} ${number(w.weight)}`).join(" · ")}</Body>
      <Muted size={12}>최대 배점은 {number(weights.filter((w) => !w.optional).reduce((sum, w) => sum + w.weight, 0))}점이에요. 방문객·공간 설명 지표는 프로필과 근거를 모두 갖춰 평가할 때만 분모에 각각 10점을 포함해요. 분모는 80·90·100점이며, 나머지 미평가·미입력 항목은 분모에 남겨 100점으로 환산해요. 표시된 전체 정합도가 높은 순으로 추천하며, 오행·일진은 별도로 평가해요.</Muted>
      <Muted size={12}>체형: 곡선→웨이브 · 직선→내추럴 · 큰 형체→스트레이트. 사진 색조: 난색→웜톤 · 한색→쿨톤. 키는 배점에 반영하지 않아요.</Muted>
      <Muted size={12}>E/I: 2025년 입장객 순위에서 많은 곳/적은 곳을 각각 선호해요. S/N: 출처를 확인한 해당 지점의 공간 설명에서 디테일·섬세·정교·세밀 / 컨셉·콘셉트·테마·세계관 문구를 확인해요. T/F: 건축물 / 자연물 중심 공간을 비교해요. 두 성격이 함께 확인되면 중립으로 평가해요.</Muted>
      <Muted size={12}>체형·MBTI 연결은 이 서비스의 취향 추천 규칙이며 과학적 적합성 판정이 아니에요. 사진 명도·채도는 사진 픽셀 기준으로, 현장 조명 실측값이 아니에요.</Muted>
      <Muted size={12}>J/P 검토안: 일정 확정 가능성 / 방문 자유도. 예약 조건·운영시간·자유 관람 근거를 갖춘 뒤 도입할 항목으로, 현재 점수에는 포함하지 않아요.</Muted>
      {weights.map((w) => <View key={w.key} style={{ gap: 3 }}>
        <Body size={13}>{w.label} · 가중치 {number(w.weight)}</Body>
        <Muted size={12}>{w.detail}</Muted>
      </View>)}
    </ScoreDisclosure>
  </Card>;
}
