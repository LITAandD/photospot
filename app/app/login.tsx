import { type TokenPair } from "@photospot/client";
import { useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Alert, Pressable, StyleSheet, Text, View } from "react-native";

import { DEMO, DEV_LOGIN } from "@/api";
import { Button, Muted, Screen, Title } from "@/components/ui";
import { useOnboarding } from "@/state/onboarding";
import { errorMessage, useAsync } from "@/hooks";
import { api } from '@/api';
import { devLogin, isAppleAvailable, isExpoGo, LoginCancelled, PROVIDERS, type ProviderId } from "@/auth/providers";
import { colors, fonts } from "@/theme";

export default function Login() {
  const router = useRouter();
  const { dispatch } = useOnboarding();
  const [busy, setBusy] = useState<ProviderId | "dev" | null>(null);
  const [apple, setApple] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(false);
  const server = useAsync(() => api.authProviders(), []);
  useEffect(() => { isAppleAvailable().then(setApple).catch(() => setApple(false)); }, []);

  const go = (pair: TokenPair) => { dispatch({ type: "reset" }); router.replace(pair.profile_exists ? "/home" : "/onboarding/basic"); };
  const run = async (id: ProviderId | "dev", fn: () => Promise<TokenPair>) => {
    if (busy || !agreed) return;
    setBusy(id); setError(null);
    try {
      go(await fn());
    } catch (e) {
      if (!(e instanceof LoginCancelled)) {
        setError(errorMessage(e));
      }
    } finally {
      setBusy(null);
    }
  };

  return (
    <Screen style={{ paddingTop: 40, gap: 28 }}>
      <Text style={s.wordmark}>포토스팟</Text>
      <View style={{ gap: 12 }}>
        <Title size={30}>로그인하고{"\n"}나의 포토 타입을 만들어요</Title>
        <Muted>내 프로필과 저장한 장소를 계정에 보관해요. 모든 프로필 항목은 선택할 수 있어요.</Muted>
      </View>
      <View style={{ flex: 1 }} />
      {error ? <Text style={{ fontFamily: fonts.body, fontSize: 13, color: colors.terracotta }}>{error}</Text> : null}
      <View style={{ gap: 10 }}>
        <Button title="개인정보 및 서비스 안내 읽기" variant="outline" onPress={() => router.push("/privacy")} />
        <Pressable accessibilityRole="checkbox" accessibilityState={{ checked: agreed }} onPress={() => setAgreed(!agreed)} style={{ paddingVertical: 12 }}>
          <Text style={{ fontFamily: fonts.body, color: colors.ink }}>{agreed ? "☑" : "□"} 서비스 이용약관과 개인정보 처리방침을 확인했어요</Text>
        </Pressable>
        {PROVIDERS.filter((p) => (p.id !== "apple" || apple) && server.data?.providers.includes(p.id)).map((p) => (
          <Pressable key={p.id} onPress={() => run(p.id, p.run)} disabled={busy !== null || !agreed} accessibilityRole="button"
            style={[s.button, { backgroundColor: p.bg, opacity: !agreed ? 0.5 : 1 }, p.id === "google" && { borderWidth: 1, borderColor: colors.lineStrong }]}>
            {busy === p.id ? <ActivityIndicator color={p.fg} /> : <Text style={[s.label, { color: p.fg }]}>{p.label}</Text>}
          </Pressable>
        ))}
        {DEV_LOGIN ? (
          <Pressable disabled={busy !== null || !agreed} onPress={() => run("dev", () => devLogin(`preview-${Date.now()}`))} accessibilityRole="button" style={[s.button, { borderWidth: 1, borderColor: colors.line, opacity: !agreed ? 0.5 : 1 }]}>
            <Text style={[s.label, { color: colors.muted }]}>체험용 로그인</Text>
          </Pressable>
        ) : null}
      </View>
      {isExpoGo ? <Muted size={12}>소셜 로그인은 설치형 개발 빌드에서 확인할 수 있어요.</Muted> : null}
      {server.error ? <Button title="로그인 서비스 다시 확인" variant="outline" onPress={server.reload}/> : null}
      {!PROVIDERS.length && !DEV_LOGIN ? <Muted>로그인 설정이 준비되지 않았어요. 설치형 앱 또는 개발 환경에서 확인해 주세요.</Muted> : null}
      <Muted size={12}>{DEMO ? "입력한 정보에 맞춰 장소를 추천해요. 프로필과 계산된 오행은 이 브라우저에 저장되며, 회원 탈퇴로 삭제할 수 있어요." : "로그인 정보는 계정 식별자와 제공된 이메일·이름만 저장해요."}</Muted>
    </Screen>
  );
}

const s = StyleSheet.create({
  wordmark: { fontFamily: fonts.display, fontSize: 20, color: colors.ink },
  button: { height: 52, borderRadius: 14, alignItems: "center", justifyContent: "center" },
  label: { fontFamily: fonts.semibold, fontSize: 15 },
});
