import { BrowseReturn } from "@/components/browse-customization";
import { browseHref, clearBrowseCustomization, pendingBrowse } from "@/browse-context";
import { type TokenPair } from "@photospot/client";
import { type Href, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";
import { ActivityIndicator, Linking, Platform, Pressable, StyleSheet, Text, View, useWindowDimensions } from "react-native";

import { DEMO, DEV_LOGIN } from "@/api";
import { Button, Muted, Screen, Title } from "@/components/ui";
import { useOnboarding } from "@/state/onboarding";
import { errorMessage, useAsync } from "@/hooks";
import { api } from '@/api';
import { devLogin, isAppleAvailable, isExpoGo, LoginCancelled, PROVIDERS, type ProviderId } from "@/auth/providers";
import { POLICY_URLS } from "@/policy-links";
import { track } from "@/analytics";
import { takeIntendedRoute } from "@/state/auth-session";
import { colors, fonts } from "@/theme";
import { BrandMark } from '@/components/brand-mark';
import { PhotoShowcase } from '@/components/photo-showcase';

type ConsentKey = "terms" | "privacy" | "age";
/** 개인정보보호법 22조: 수집·이용 동의는 약관 동의와 구분해 받고 항목·목적·보유기간을 함께 보여준다. 위치정보 동의는 홈의 '내 주변에서 찾기'에서 따로 받는다 */
const CONSENTS: { key: ConsentKey; title: string; detail?: string; link?: "terms" | "privacy" }[] = [
  { key: "terms", title: "[필수] 서비스 이용약관 동의", link: "terms" },
  { key: "privacy", title: "[필수] 개인정보 수집·이용 동의", link: "privacy",
    detail: DEMO ? "항목: 성별·출생연도·키·체형·퍼스널컬러·MBTI(모두 선택) · 목적: 장소 추천\n보유: 이 브라우저에만 저장, 설정에서 이 브라우저의 데이터 삭제 시 즉시 파기"
      : "항목: 로그인 계정 식별자·이메일·이름, 성별·출생연도·키·체형·퍼스널컬러·MBTI(선택) · 목적: 계정 관리·장소 추천\n보유: 회원 탈퇴 시까지, 탈퇴 즉시 파기" },
  { key: "age", title: "[필수] 만 14세 이상입니다", detail: DEMO ? "맞춤 추천은 만 14세 이상만 이용할 수 있어요" : "만 14세 미만은 가입할 수 없어요" },
];
const NONE: Record<ConsentKey, boolean> = { terms: false, privacy: false, age: false };

function ConsentRow({ checked, title, detail, onToggle, onOpen }: { checked: boolean; title: string; detail?: string; onToggle: () => void; onOpen?: () => void }) {
  return (
    <View style={s.consentRow}>
      <Pressable accessibilityRole="checkbox" accessibilityState={{ checked }} aria-checked={checked} accessibilityLabel={title} onPress={onToggle}
        {...(Platform.OS === 'web' ? { onKeyDown: (event: React.KeyboardEvent) => {
          if (event.key === ' ') { event.preventDefault(); if (!event.repeat) onToggle(); }
        } } : {})} style={s.consentMain}>
        <Text style={s.checkbox}>{checked ? "☑" : "□"}</Text>
        <View style={{ flex: 1, gap: 2 }}>
          <Text style={s.consentTitle}>{title}</Text>
          {detail ? <Text style={s.consentDetail}>{detail}</Text> : null}
        </View>
      </Pressable>
      {onOpen ? <Pressable accessibilityRole="link" accessibilityLabel={`${title} 전문 보기`} onPress={onOpen} style={s.consentLink}><Text style={s.consentLinkText}>보기</Text></Pressable> : null}
    </View>
  );
}

export default function Login() {
  const router = useRouter();
  const wide = useWindowDimensions().width >= 840;
  const { dispatch } = useOnboarding();
  const [busy, setBusy] = useState<ProviderId | "dev" | null>(null);
  const [apple, setApple] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [agreed, setAgreed] = useState(NONE);
  const allAgreed = CONSENTS.every((c) => agreed[c.key]);
  const openPolicy = (key: "terms" | "privacy") => {
    const url = POLICY_URLS[key];
    if (url) Linking.openURL(url).catch(() => router.push("/privacy")); else router.push("/privacy");
  };
  const server = useAsync(() => api.authProviders(), []);
  useEffect(() => { isAppleAvailable().then(setApple).catch(() => setApple(false)); }, []);

  // 필수 동의 3개를 모두 받은 로그인만 여기 온다(동의 내용·개인정보는 보내지 않음). 프로필이 있으면 기억해 둔 딥링크로 바로 돌아가 /home 이 잠깐 보이지 않게 한다.
  const go = (pair: TokenPair) => {
    void track("consent_accept", { terms: true, privacy: true, age: true });
    dispatch({ type: "reset" });
    const destination = pair.profile_exists ? (takeIntendedRoute() as Href | null) ?? "/home" : "/onboarding/basic";
    if (pair.profile_exists) clearBrowseCustomization();
    router.replace(destination);
  };
  const run = async (id: ProviderId | "dev", fn: () => Promise<TokenPair>) => {
    if (busy || !allAgreed) return;
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
    <Screen wide style={{ paddingTop: wide ? 40 : 22, gap: wide ? 56 : 26 }}>
      <View style={s.header}><BrandMark/><Pressable accessibilityRole="button" onPress={()=>router.replace('/')} style={s.back}><Text style={s.backLabel}>처음 화면 ↗</Text></Pressable></View>
      <View style={[s.content, wide && { flexDirection: 'row', alignItems: 'center', gap: 56 }]}>
      {wide ? <View style={{ flex: 1 }}><PhotoShowcase height={430}/></View> : null}
      <View style={{ flex: wide ? 1 : undefined, gap: 22 }}>
      <BrowseReturn />
      <View style={{ gap: 14 }}>
        <Text style={s.eyebrow}>YOUR NEXT PHOTO STARTS HERE</Text>
        <Title size={30}>{DEMO ? "웹에서 나의\n포토 타입을 만들어요" : "로그인하고\n나의 포토 타입을 만들어요"}</Title>
        <Muted>{DEMO ? "계정 생성 없이 시작해요. 프로필과 저장한 장소는 이 브라우저에만 보관하며, 다른 기기와 동기화되지 않아요. 모든 프로필 항목은 선택이에요." : "내 프로필과 저장한 장소를 계정에 보관해요. 모든 프로필 항목은 선택할 수 있어요."}</Muted>
      </View>
      {!wide ? <PhotoShowcase compact height={150}/> : null}
      {DEMO ? <Button title="개인정보 입력 없이 장소 둘러보기" variant="outline" onPress={() => { const context = pendingBrowse(); clearBrowseCustomization(true); router.dismissTo(context ? browseHref(context) : "/browse"); }} /> : null}
      {error ? <Text accessibilityRole="alert" style={{ fontFamily: fonts.body, fontSize: 13, color: colors.terracotta }}>{error}</Text> : null}
      <View style={{ gap: 10 }}>
        <Pressable accessibilityRole="link" accessibilityLabel="개인정보 및 서비스 안내 읽기" onPress={()=>router.push('/privacy')} style={{ minHeight: 44, justifyContent: 'center' }}><Text style={s.policyLink}>개인정보 및 서비스 안내 읽기 ↗</Text></Pressable>
        <View style={s.consents}>
          <ConsentRow checked={allAgreed} title="모두 동의" onToggle={() => setAgreed(allAgreed ? NONE : { terms: true, privacy: true, age: true })} />
          <View style={s.consentDivider} />
          {CONSENTS.map((c) => <ConsentRow key={c.key} checked={agreed[c.key]} title={c.title} detail={c.detail} onToggle={() => setAgreed({ ...agreed, [c.key]: !agreed[c.key] })} onOpen={c.link ? () => openPolicy(c.link!) : undefined} />)}
          <Muted size={12}>위치정보 이용은 추천 화면에서 '내 주변에서 찾기'를 누를 때 따로 동의받아요.</Muted>
        </View>
        {PROVIDERS.filter((p) => (p.id !== "apple" || apple) && server.data?.providers.includes(p.id)).map((p) => (
          <Pressable key={p.id} onPress={() => run(p.id, p.run)} disabled={busy !== null || !allAgreed} accessibilityRole="button" accessibilityState={{ disabled: busy !== null || !allAgreed }}
            style={[s.button, { backgroundColor: p.bg, opacity: !allAgreed ? 0.5 : 1 }, p.id === "google" && { borderWidth: 1, borderColor: colors.lineStrong }]}>
            {busy === p.id ? <ActivityIndicator color={p.fg} /> : <Text style={[s.label, { color: p.fg }]}>{p.label}</Text>}
          </Pressable>
        ))}
        {DEV_LOGIN ? (
          <Pressable disabled={busy !== null || !allAgreed} onPress={() => run("dev", () => devLogin(`preview-${Date.now()}`))} accessibilityRole="button" accessibilityState={{disabled: busy !== null || !allAgreed, busy: busy === 'dev'}} style={[s.button, { backgroundColor: colors.accent, borderWidth: 1, borderColor: colors.accentBorder, opacity: !allAgreed ? 0.45 : 1 }]}>
            {busy === 'dev' ? <ActivityIndicator color={colors.onAccent}/> : <Text style={[s.label, { color: colors.onAccent }]}>{DEMO ? '추천 시작하기' : '체험용 로그인'}</Text>}
          </Pressable>
        ) : null}
      </View>
      {isExpoGo ? <Muted size={12}>소셜 로그인은 설치형 개발 빌드에서 확인할 수 있어요.</Muted> : null}
      {server.error ? <Button title="로그인 서비스 다시 확인" variant="outline" onPress={server.reload}/> : null}
      {!PROVIDERS.length && !DEV_LOGIN ? <Muted>로그인 설정이 준비되지 않았어요. 설치형 앱 또는 개발 환경에서 확인해 주세요.</Muted> : null}
      <Muted size={12}>{DEMO ? "입력한 정보에 맞춰 장소를 추천해요. 저장된 정보는 내 정보 · 설정의 ‘이 브라우저의 데이터 삭제’에서 지울 수 있어요." : "로그인 정보는 계정 식별자와 제공된 이메일·이름만 저장해요."}</Muted>
      </View>
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', alignItems: 'center', justifyContent: 'space-between' },
  back: { minHeight: 44, justifyContent: 'center' },
  backLabel: { fontFamily: fonts.medium, fontSize: 12, color: colors.muted },
  content: { gap: 24 },
  eyebrow: { fontFamily: fonts.semibold, fontSize: 10, letterSpacing: 1.7, color: colors.secondaryInk },
  button: { minHeight: 56, padding: 14, borderRadius: 16, alignItems: "center", justifyContent: "center" },
  label: { fontFamily: fonts.semibold, fontSize: 15 },
  consents: { gap: 2, paddingVertical: 4 },
  consentDivider: { height: 1, backgroundColor: colors.line, marginVertical: 4 },
  consentRow: { flexDirection: "row", alignItems: "center", gap: 4 },
  consentMain: { flex: 1, flexDirection: "row", alignItems: "flex-start", gap: 8, minHeight: 44, paddingVertical: 8 },
  checkbox: { fontFamily: fonts.body, fontSize: 18, lineHeight: 22, color: colors.ink },
  consentTitle: { fontFamily: fonts.body, fontSize: 14, lineHeight: 22, color: colors.ink },
  consentDetail: { fontFamily: fonts.body, fontSize: 12, lineHeight: 18, color: colors.muted },
  consentLink: { minHeight: 44, minWidth: 44, justifyContent: "center", alignItems: "center" },
  consentLinkText: { fontFamily: fonts.body, fontSize: 13, color: colors.accentInk, textDecorationLine: "underline" },
  policyLink: { fontFamily: fonts.medium, fontSize: 12, color: colors.accentInk },
});
