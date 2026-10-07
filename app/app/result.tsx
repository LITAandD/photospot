import { useRouter } from "expo-router";
import React from "react";
import { ActivityIndicator, Share, StyleSheet, Text, View } from "react-native";

import { api } from "@/api";
import { Body, Button, ErrorBox, Label, Muted, Screen, Title } from "@/components/ui";
import { errorMessage, useAsync } from "@/hooks";
import { colors, fonts } from "@/theme";
import { ProfileSummary } from "@/components/profile-summary";

export default function Result() {
  const router = useRouter();
  const card = useAsync(() => api.getTypeCard(), []);
  const profile = useAsync(() => api.getProfile(), []);
  const share = () => card.data && Share.share({
    message: `나의 포토 타입: ${card.data.name}\n잘 맞는 빛: ${card.data.best_light.join(", ")}\n어울리는 배경: ${card.data.good_backgrounds.join(", ")}`,
  });
  const Row = ({ label, items }: { label: string; items: string[] }) => items.length ? (
    <View style={s.row}><Label>{label}</Label><Body>{items.join(", ")}</Body></View>
  ) : null;
  return (
    <Screen style={{ paddingTop: 32 }}>
      <Text style={s.eyebrow}>나의 포토 타입</Text>
      {card.loading ? <ActivityIndicator color={colors.accent} /> : null}
      {card.error ? <ErrorBox message={errorMessage(card.error)} onRetry={card.reload} /> : null}
      {profile.data ? <ProfileSummary profile={profile.data} /> : null}
      {card.data ? (
        <View style={s.card}>
          <View style={s.cardHead}>
            <Title size={30}>{card.data.name}</Title>
            <Muted>{card.data.subtitle}</Muted>
          </View>
          <View style={{ paddingHorizontal: 24, paddingBottom: 8 }}>
            <Row label="나를 살리는 빛" items={card.data.best_light} />
            <Row label="어울리는 배경" items={card.data.good_backgrounds} />
            <Row label="피하면 좋은 곳" items={card.data.avoid} />
            {card.data.lucky ? <Row label="가장 강한 기운 · 사주" items={[card.data.lucky]} /> : null}
          </View>
        </View>
      ) : null}
      <View style={{ flex: 1 }} />
      <Button title="추천 장소 보기" onPress={() => router.replace("/home")} />
      <Button title="결과 카드 공유하기" variant="outline" onPress={share} disabled={!card.data} />
    </Screen>
  );
}

const s = StyleSheet.create({
  eyebrow: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accent, textAlign: "center" },
  card: { borderRadius: 20, overflow: "hidden", backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line },
  cardHead: { gap: 10, padding: 24, backgroundColor: "#E9ECF2" },
  row: { gap: 4, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
});
