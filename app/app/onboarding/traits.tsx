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
  [2, "T", "건축·구도", "F", "감성·분위기"],
  [3, "J", "계획형 코스", "P", "산책형 동네"],
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
        <Muted>MBTI는 장소의 분위기를 고르는 참고 정보예요. 사주 오행은 나중에 촬영 날짜를 정할 때 선택할 수 있어요.</Muted>
      </View>
      <View style={{ gap: 10 }}>
        <Label>MBTI</Label>
        {PAIRS.map(([pos, a, ad, b, bd]) => (
          <View key={pos} style={{ flexDirection: "row", gap: 8 }}>
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
        ))}
      </View>
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
