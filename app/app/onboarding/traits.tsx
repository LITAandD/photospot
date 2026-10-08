import { finishOnboarding } from "@photospot/client";
import { useRouter } from "expo-router";
import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "@/api";
import { Button, ErrorBox, Label, Muted, Screen, StepHeader, Title } from "@/components/ui";
import { errorMessage } from "@/hooks";
import { toOnboarding, useOnboarding } from "@/state/onboarding";
import { colors, fonts } from "@/theme";

const PAIRS: [number, string, string, string, string][] = [
  [0, "E", "활기찬 곳", "I", "한적한 곳"],
  [1, "S", "디테일 맛집", "N", "컨셉 공간"],
  [2, "T", "건축 공간", "F", "자연·경관"],
  [3, "J", "일정 확정", "P", "자유 방문"],
];

const CRITERIA = [
  "2025년 입장객 수와 집계 장소 내 순위 · 실시간 혼잡도는 아니에요",
  "네이버지도·인스타그램의 공간 설명·리뷰에서 디테일 / 컨셉 문구 확인",
  "지도 유형·태그로 건축물 중심 / 자연물 중심 공간 분류",
  "검토안 · 예약·운영시간 / 자유 관람 조건으로 판단 예정, 현재 배점 제외",
];

export default function Traits() {
  const router = useRouter();
  const { draft, dispatch } = useOnboarding();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  // 네 글자가 다 모이기 전까지는 화면에서만 들고 있다가, 완성되면 초안에 저장
  const [current, setCurrent] = useState(draft.profile.mbti ?? "____");
  const pick = (pos: number, letter: string) => {
    const chars = current.split("");
    chars[pos] = letter;
    const next = chars.join("");
    setCurrent(next);
    dispatch({ type: "profile", patch: { mbti: next.includes("_") ? null : next } });
  };

  const submit = async (skipTraits = false) => {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await finishOnboarding(api, toOnboarding(skipTraits ? { ...draft, profile: { ...draft.profile, mbti: null } } : draft));
      dispatch({ type: "reset" });
      router.replace("/result");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <StepHeader step={3} total={3} backHref="/onboarding/style" onSkip={() => submit(true)} disabled={busy} />
      <View style={{ gap: 8 }}>
        <Label>3 / 3 · 선택</Label>
        <Title>성향을 더해볼까요</Title>
        <Muted>MBTI를 촬영 장소 취향에 연결해요. E/I·S/N·T/F 각 10점, 총 30점을 반영하며 근거가 없는 항목은 미평가로 남겨요.</Muted>
      </View>
      <View style={{ gap: 10 }}>
        <Label>MBTI</Label>
        {PAIRS.map(([pos, a, ad, b, bd]) => (
          <View key={pos} style={{ gap: 6 }}>
          <View style={{ flexDirection: "row", gap: 8 }}>
            {[[a, ad], [b, bd]].map(([letter, desc]) => {
              const on = current[pos] === letter;
              return (
                <Pressable key={letter} onPress={() => pick(pos, letter)} accessibilityRole="button" accessibilityState={{ selected: on }}
                  style={[s.pair, on && { borderColor: colors.accent, backgroundColor: colors.accentSoft }]}>
                  <Text style={[s.letter, on && { color: colors.accentInk }]}>{letter}</Text>
                  <Muted size={13}>{desc}</Muted>
                </Pressable>
              );
            })}
          </View>
          <Muted size={11}>{CRITERIA[pos]}</Muted>
          </View>
        ))}
      </View>
      <Muted size={12}>이 연결은 포토스팟의 장소 취향 기준이에요. 성격에 따라 촬영 취향이 정해지는 것은 아니므로 원하는 성향을 선택해 주세요.</Muted>
      <View style={{ flex: 1 }} />
      <Muted size={12}>추천 받기를 누르면 선택한 프로필 정보를 맞춤 추천에 사용하고 저장해요. 모든 항목은 선택이며 설정에서 수정·삭제할 수 있어요.</Muted>
      {error ? <ErrorBox message={error} /> : null}
      <Button title="추천 받기" onPress={() => submit()} loading={busy} />

    </Screen>
  );
}

const s = StyleSheet.create({
  pair: { flex: 1, height: 48, paddingHorizontal: 14, borderRadius: 12, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card, flexDirection: "row", alignItems: "center", gap: 8 },
  letter: { fontFamily: fonts.semibold, fontSize: 16, color: colors.ink },
  cardTitle: { fontFamily: fonts.semibold, fontSize: 15, color: colors.ink },
  checkbox: { width: 20, height: 20, borderRadius: 5, borderWidth: 1.5, borderColor: colors.lineStrong, marginTop: 1 },
});
