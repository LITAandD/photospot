import { useLocalSearchParams, useRouter } from "expo-router";
import { naverMapUrl } from "@photospot/client";
import React, { useState } from "react";
import { ActivityIndicator, Linking, View } from "react-native";

import { api, DEMO } from "@/api";
import { PhotoCredit } from "@/components/place-photo";
import { PlacePoseGuide } from "@/components/place-pose-guide";
import { PlaceGallery } from "@/components/place-gallery";
import { InstagramPosts } from "@/components/instagram-posts";
import { PlaceElements } from "@/components/place-elements";
import { DiscoveryDetails } from "@/components/place-discovery";
import { PlaceHours } from "@/components/place-hours";
import { Body, Button, Card, ErrorBox, Label, Muted, Screen, ScoreBar, Title } from "@/components/ui";
import { errorMessage, useAsync } from "@/hooks";
import { colors } from "@/theme";
import { RecommendationBadge } from "@/components/recommendation-badge";
import { ScoreDetails, ScoringGuide } from "@/components/score-explanation";

export default function Place() {
  const { id, rec, date, spot, scene, saju } = useLocalSearchParams<{ id: string; rec?: string; date?: string; spot?: string; scene?: string; saju?: string }>();
  const router = useRouter();
  const place = useAsync(() => api.getPlace(id, date, saju === "1"), [id, date, saju]);
  const p = place.data;
  const best = [p?.best_scene, ...(p?.other_scenes ?? [])].find((s) => s?.scene_id === scene) ?? p?.best_scene ?? null;
  const cover = p?.photos[0];
  const mapUrl = naverMapUrl(p?.name, p?.links.naver_map_url);
  const saved = useAsync(() => api.getBookmarks(), [id]);
  const isSaved = !!saved.data?.some((b) => b.place_id === id);
  const [saving, setSaving] = useState(false);
  const [actionError, setActionError] = useState<string | null>(null);
  const toggleSaved = async () => {
    if (saving) return;
    setSaving(true); setActionError(null);
    try { if (isSaved) await api.removeBookmark(id); else await api.saveBookmark(id); saved.reload(); }
    catch (e) { setActionError(errorMessage(e)); }
    finally { setSaving(false); }
  };

  return (
    <Screen style={{ paddingHorizontal: 0, paddingTop: 0 }}>
      {!cover && p?.instagram_posts?.length ? <View style={{ paddingHorizontal: 24, paddingTop: 12 }}>
        <Button title="‹ 추천 목록" variant="outline" onPress={() => router.canGoBack() ? router.back() : router.replace("/home")} />
      </View> : <PlacePoseGuide key={cover?.url ?? id} photo={cover} name={p?.name}
        onBack={() => router.canGoBack() ? router.back() : router.replace("/home")} />}
      <View style={{ paddingHorizontal: 24, gap: 24 }}>
        {place.loading ? <ActivityIndicator color={colors.accent} /> : null}
        {place.error ? <ErrorBox message={errorMessage(place.error)} onRetry={place.reload} /> : null}
        {p ? (
          <>
            <View style={{ gap: 8 }}>
              <View style={{ flexDirection: "row", justifyContent: "space-between", alignItems: "center", gap: 12 }}>
                <View style={{ flex: 1 }}><Title>{p.name}</Title></View>
                <RecommendationBadge score={best?.scoring ? best.scoring.score : p.scoring ? p.scoring.score : best?.reasons.length ? best.score : p.fit_score} saju={saju === "1"} elements={best?.recommended_elements ?? p.recommended_elements} />
              </View>
              <Muted>{p.address ?? p.category}{best ? ` · 추천 장면: ${SLOT[best.time_slot] ?? best.time_slot}, ${best.spot_name}` : ""}</Muted>
              {best ? <Muted size={12}>{best.evidence === "human" ? "검수 확정 태그" : `사진 ${best.photo_count ?? 0}장 분석 · 신뢰도 ${Math.round((best.confidence ?? 0) * 100)}%`}</Muted> : null}
              {cover ? <PhotoCredit photo={cover} /> : null}
            </View>
            <InstagramPosts key={id} posts={p.instagram_posts ?? []} />
            <PlaceHours place={p} />
            <PlaceGallery key={id} photos={p.photos} />
            <DiscoveryDetails evidence={p.discovery} />
            <PlaceElements profile={p.element_profile} />
            {saju === "1" && p.saju_match ? <Card style={{ gap: 8 }}>
              <Body>오행 종합 {p.saju_match.score}점 · {p.saju_match.label} 기준</Body>
              <Muted>내 오행 비율 {p.saju_match.personal_percent}% · 개인 보완 {p.saju_match.personal_points}/70 + 일진 관계 {p.saju_match.day_points}/30</Muted>
              <Muted>{p.saju_match.day_relation_label}</Muted>
              <Muted size={12}>이 점수는 선택한 촬영일의 오행 탐색 기준이에요. 사진 정합도와는 별도로 계산해요.</Muted>
            </Card> : null}
            <ScoreDetails scoring={best?.scoring ?? p.scoring} />
            <ScoringGuide weights={p.score_weights} />
            {p.discovery_reasons?.length ? <Card style={{ gap: 8 }}>
              <Label>추천 이유</Label>
              {p.discovery_reasons.map((reason) => <Body key={reason.label} size={14}>{reason.label}</Body>)}
              <Muted size={12}>사진 특징·공간 설명·건축과 자연·2025년 방문객 통계를 프로필과 비교해요. 전체 기본 배점을 기준으로 계산하며 미평가 항목은 확인 전까지 점수를 더하지 않아요. 오행·일진은 별도로 평가해요.</Muted>
            </Card> : null}
            {!best?.scoring && !p.scoring && best && best.reasons.length ? (
              <View style={{ gap: 12 }}>
                <Label>나와 맞는 이유</Label>
                <Card style={{ gap: 10 }}>
                  {best.reasons.map((r) => <ScoreBar key={r.label} label={r.label} points={r.points} auxiliary={r.layer === "auxiliary"} />)}
                  <View style={{ flexDirection: "row", gap: 16, paddingTop: 6 }}>
                    <Muted size={12}>■ 사진발 (실용)</Muted><Muted size={12}>■ 성향 (보조)</Muted>
                  </View>
                </Card>
              </View>
            ) : null}
            <View style={{ gap: 12 }}>
              <Label>방문 전 확인</Label>
              {!p.hours && p.opening_hours ? <Body size={14}>원본 지도에 등록된 시간: {p.opening_hours}</Body> : null}
              {p.visit_notes.map((n) => <Body key={n} size={14}>{n}</Body>)}
            </View>
            <View style={{ gap: 10 }}>
              {p.source ? <Muted size={11}>{p.source.label}</Muted> : null}
              {actionError ? <ErrorBox message={actionError} /> : null}
              {saved.error ? <ErrorBox message={errorMessage(saved.error)} onRetry={saved.reload} /> : null}
              {p.source?.url ? <Button title="원본 지도에서 장소 확인" variant="outline" onPress={() => Linking.openURL(p.source!.url!).catch(() => setActionError("원본 지도를 열지 못했어요"))} /> : null}
              <View style={{ flexDirection: "row", gap: 10 }}>
                <View style={{ flex: 1 }}>
                  <Button title="네이버 지도" variant="outline" disabled={!mapUrl}
                    onPress={() => { if (mapUrl) Linking.openURL(mapUrl).catch(() => setActionError("지도를 열지 못했어요. 다시 시도해 주세요")); }} />
                </View>
                <View style={{ flex: 1 }}><Button title={isSaved ? "저장됨 ♥" : "저장 ♡"} variant="outline" onPress={toggleSaved} loading={saving} disabled={saved.loading || !!saved.error} /></View>
              </View>
              {!mapUrl ? <Muted size={12}>장소명이 아직 없어 네이버지도 검색을 준비 중이에요. 원본 지도에서 위치를 확인할 수 있어요.</Muted> : null}
              {rec && best ? (
                <Button title="다녀왔어요" onPress={() => router.push({ pathname: "/feedback/[recId]", params: { recId: rec, name: p.name, spot: spot ?? best.spot_id } })} />
              ) : null}
            </View>
          </>
        ) : null}
      </View>
    </Screen>
  );
}

const SLOT: Record<string, string> = { morning: "아침", midday: "낮", golden_hour: "골든아워", night: "밤" };
