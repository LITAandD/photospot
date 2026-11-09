import { useRouter } from "expo-router";
import React, { useEffect } from "react";
import { ActivityIndicator, StyleSheet, Text, View } from "react-native";

import { api } from "@/api";
import { track } from "@/analytics";
import { Body, Button, ErrorBox, Label, Muted, Screen, Title, Toast } from "@/components/ui";
import { errorMessage, useAsync, useToast } from "@/hooks";
import { SHARE_NOTICE, shareLine, shareText, shareUrl } from "@/share";
import { colors, fonts } from "@/theme";
import { ProfileSummary } from "@/components/profile-summary";

export default function Result() {
  const router = useRouter();
  const card = useAsync(() => api.getTypeCard(), []);
  const profile = useAsync(() => api.getProfile(), []);
  const [notice, showNotice] = useToast();
  // 퍼스널컬러·체형이 없으면 서버가 '아직 타입을 알 수 없어요' 자리표시 카드를 준다. 이 카드는 공유하지 않는다
  const placeholder = !!card.data && !card.data.best_light.length && !card.data.good_backgrounds.length && !card.data.avoid.length;
  useEffect(() => { if (card.data) void track("result_view", { known: !placeholder }); }, [card.data, placeholder]);
  const share = async () => {
    if (!card.data || placeholder) return;
    const outcome = await shareText({
      title: `나의 포토 타입 · ${card.data.name}`,
      lines: [`나의 포토 타입: ${card.data.name}`, card.data.subtitle, shareLine("잘 맞는 빛", card.data.best_light),
        shareLine("어울리는 배경", card.data.good_backgrounds), shareLine("피하면 좋은 곳", card.data.avoid), "포토스팟에서 나에게 어울리는 촬영 장소를 찾아보세요"],
      url: shareUrl("/", "share", { utm_medium: "result_card" }),
    });
    void track("share_click", { surface: "result", outcome });
    showNotice(SHARE_NOTICE[outcome]);
  };
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
      <Toast message={notice} />
      <Button title="추천 장소 보기" onPress={() => router.replace("/home")} />
      {placeholder
        ? <Button title="프로필 입력하고 타입 보기" variant="outline" onPress={() => router.push("/settings")} />
        : <Button title="결과 카드 공유하기" variant="outline" onPress={() => { void share(); }} disabled={!card.data} />}
    </Screen>
  );
}

const s = StyleSheet.create({
  eyebrow: { fontFamily: fonts.semibold, fontSize: 13, color: colors.accent, textAlign: "center" },
  card: { borderRadius: 20, overflow: "hidden", backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line },
  cardHead: { gap: 10, padding: 24, backgroundColor: "#E9ECF2" },
  row: { gap: 4, paddingVertical: 14, borderBottomWidth: 1, borderBottomColor: colors.divider },
});
