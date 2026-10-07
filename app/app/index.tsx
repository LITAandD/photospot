import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";

import { api } from "@/api";
import { StyleSheet, Text, View } from "react-native";

import { Button, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { errorMessage } from "@/hooks";
import { colors, fonts } from "@/theme";

const TEASERS = [
  { color: "#E4E8EE", title: "부드러운 자연광 · 곡선 공간", who: "여름 쿨 · 웨이브에게" },
  { color: "#D9B88C", title: "골든아워 · 넓은 들판", who: "가을 웜 · 내추럴에게" },
  { color: "#1E2A44", title: "선명한 야경 · 매끈한 건축", who: "겨울 쿨 · 스트레이트에게" },
];

export default function Welcome() {
  const router = useRouter();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  useEffect(() => { api.auth.isSignedIn().then(setSignedIn).catch(() => setSignedIn(false)); }, []);
  const start = async () => {
    if (!signedIn) return router.push("/login");
    setBusy(true); setError(null);
    try {
      const profile = await api.getProfile();
      router.replace(profile.profile_exists ? "/home" : "/onboarding/basic");
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  return (
    <Screen style={{ paddingTop: 40, gap: 28 }}>
      <Text style={s.wordmark}>포토스팟</Text>
      <View style={{ gap: 14 }}>
        <Title size={34}>나에게 어울리는{"\n"}빛과 배경을 찾아요</Title>
        <Muted size={15}>퍼스널컬러와 체형으로 사진이 잘 나오는 장소를 추천해요. MBTI와 사주는 원하면 더할 수 있어요.</Muted>
      </View>
      <View style={{ flex: 1, justifyContent: "center", gap: 10 }}>
        {TEASERS.map((t, i) => (
          <View key={t.title} style={[s.teaser, i === 1 && { marginLeft: 20 }]}>
            <View style={[s.thumb, { backgroundColor: t.color }]} />
            <View style={{ gap: 4 }}>
              <Text style={s.teaserTitle}>{t.title}</Text>
              <Muted size={13}>{t.who}</Muted>
            </View>
          </View>
        ))}
      </View>
      <View style={{ gap: 12 }}>
        {error ? <ErrorBox message={error} /> : null}
        <Button title={signedIn ? "계속하기" : "시작하기"} onPress={start} disabled={signedIn === null} loading={busy} />
        <Text style={{ textAlign: "center", fontFamily: fonts.body, fontSize: 13, color: colors.muted }}>모든 항목은 건너뛸 수 있어요</Text>
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  wordmark: { fontFamily: fonts.display, fontSize: 20, color: colors.ink },
  teaser: { flexDirection: "row", alignItems: "center", gap: 14, padding: 14, backgroundColor: colors.card, borderWidth: 1, borderColor: colors.line, borderRadius: 16 },
  thumb: { width: 64, height: 64, borderRadius: 12 },
  teaserTitle: { fontFamily: fonts.semibold, fontSize: 15, color: colors.ink },
});
