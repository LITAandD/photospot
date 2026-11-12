import * as Linking from "expo-linking";
import { Stack, usePathname, useRouter, type ErrorBoundaryProps, type Href } from "expo-router";
import React, { useEffect, useRef, useState } from "react";

import { api, DEMO, onSignedOut } from "@/api";
import { captureUtm, reportClientError, setAnalyticsRoute, track } from "@/analytics";
import { Button, Muted, Title } from "@/components/ui";
import { clearIntendedRoute, hrefFromUrl, onSessionChange, peekIntendedRoute, rememberIntendedRoute } from '@/state/auth-session';
import { readDraft, sameProfile, touchedFields, writeDraft } from "@/state/draft-store";
import { PUBLIC_WEB_URL } from "@/share";
import { useAppFonts } from "@/fonts";
import { Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { initialDraft, OnboardingProvider, useOnboarding } from "@/state/onboarding";
import { takeSignOutRoute } from "@/state/sign-out";
import { colors, fonts } from "@/theme";
import type { Profile, ProfileOut } from "@photospot/client";

export default function RootLayout() {
  const loaded = useAppFonts();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const session = useRef<boolean | null>(null);
  session.current = signedIn;
  const initialHref = useRef<string | null>(null);
  useEffect(() => {
    let active = true, changed = false;
    const unsubscribe = onSessionChange(value => { changed = true; if (active) setSignedIn(value); });
    api.auth.isSignedIn().then(value => { if (active && !changed) setSignedIn(value); })
      .catch(() => { if (active && !changed) setSignedIn(false); });
    // 진입 주소: utm_* 는 계측에 붙이고, 비로그인이면 딥링크를 로그인·온보딩 뒤 돌아가도록 기억한다(F023).
    // 로그인 상태면 라우터가 바로 그 화면을 열므로 기억하지 않는다 (나중에 /home 에서 엉뚱하게 되돌아가지 않게)
    const remember = (url: string | null) => {
      captureUtm(url);
      const href = hrefFromUrl(url);
      if (!href) return;
      if (session.current === false) rememberIntendedRoute(href); else if (session.current === null) initialHref.current = href;
    };
    Linking.getInitialURL().then(url => { if (active) remember(url); }).catch(() => undefined);
    const link = Linking.addEventListener("url", ({ url }) => remember(url));
    return () => { active = false; unsubscribe(); link.remove(); };
  }, []);
  useEffect(() => {
    if (signedIn === false && initialHref.current) rememberIntendedRoute(initialHref.current);
    if (signedIn !== null) initialHref.current = null;
  }, [signedIn]);
  // Protected screens cannot start GPS/requests before checking the session.
  if (!loaded || signedIn === null) return null;
  return (
    <SafeAreaProvider>
      <OnboardingProvider>
        <SessionListener />
        <RouteListener />
        <DeepLinkKeeper signedIn={signedIn} />
        <OnboardingKeeper signedIn={signedIn} />
        {DEMO ? <DemoBanner /> : null}
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
          <Stack.Screen name="login" />
          <Stack.Screen name="index" />
          <Stack.Screen name="privacy" />
          <Stack.Screen name="browse" />
          <Stack.Screen name="oauth/naver" />
          <Stack.Screen name="+not-found" />
          <Stack.Protected guard={signedIn}>
            {['home', 'saju', 'saved', 'settings', 'result', 'support', 'accounts', 'admin', 'feedback',
              'feedback/[recId]', 'place/[id]', 'diagnosis/[kind]', 'onboarding/basic', 'onboarding/style',
              'onboarding/traits'].map(name => <Stack.Screen key={name} name={name} />)}
          </Stack.Protected>
        </Stack>
      </OnboardingProvider>
    </SafeAreaProvider>
  );
}

/**
 * 화면 어디서든 잡히지 않은 렌더 오류가 나면 앱이 꺼지는 대신 이 화면을 보여준다 (expo-router가 라우트 트리를 <Try>로 감싼다).
 * 통계에 별도 동의한 경우에만 오류 이름·플랫폼·경로를 client_error로 보낸다. 오류 메시지와 스택은 전송하지 않는다.
 */
export function ErrorBoundary({ error, retry }: ErrorBoundaryProps) {
  const [busy, setBusy] = useState(false);
  useEffect(() => { void reportClientError(error); }, [error]);
  return (
    <SafeAreaProvider>
      <View style={{ flex: 1, backgroundColor: colors.bg, padding: 24, justifyContent: "center", gap: 16 }} accessibilityRole="alert" accessibilityLiveRegion="assertive">
        <Title size={24}>화면을 표시하지 못했어요</Title>
        <Muted>일시적인 문제일 수 있어요. 다시 시도해도 반복되면 앱을 완전히 종료한 뒤 다시 열어 주세요.</Muted>
        {__DEV__ ? <Text style={{ fontFamily: fonts.body, fontSize: 12, color: colors.terracotta }}>{error.message}</Text> : null}
        <Button title="다시 시도" loading={busy} onPress={() => { setBusy(true); Promise.resolve(retry()).finally(() => setBusy(false)); }} />
      </View>
    </SafeAreaProvider>
  );
}

function SessionListener() {
  const router = useRouter();
  const { dispatch } = useOnboarding();
  useEffect(() => onSignedOut(() => { dispatch({ type: "reset" }); void writeDraft(null); router.replace(takeSignOutRoute()); }), [router, dispatch]);
  return null;
}

/**
 * 경로 변경: 계측에 현재 경로를 기록하고 대문 진입만 이벤트로 남긴다 (쿼리·개인정보 없음).
 * 웹은 빌드가 넣은 canonical·og:url(대문 주소)을 현재 경로로 맞춘다 — 한 HTML 을 모든 경로가 공유하므로 (scripts/build-web-preview.cjs)
 */
function RouteListener() {
  const pathname = usePathname();
  useEffect(() => {
    setAnalyticsRoute(pathname);
    if (pathname === "/") void track("landing_view");
    if (typeof document !== "undefined") {
      const href = `${PUBLIC_WEB_URL}${pathname.startsWith("/") ? pathname : `/${pathname}`}`;
      document.querySelector('link[rel="canonical"]')?.setAttribute("href", href);
      document.querySelector('meta[property="og:url"]')?.setAttribute("content", href);
    }
  }, [pathname]);
  return null;
}

/**
 * 기억해 둔 딥링크로 돌려보낸다. 로그인 화면은 프로필 유무에 따라 /home·/onboarding/basic 으로 보내므로,
 * /home 에 닿으면 가려던 곳으로 바꾸고, 온보딩이 필요한 경우는 traits 가 완료 뒤 꺼내 쓴다 (index.tsx 도 같은 저장소를 본다).
 */
const HOLDING = /^\/(login|onboarding\/|oauth\/|privacy)/;
function DeepLinkKeeper({ signedIn }: { signedIn: boolean }) {
  const router = useRouter();
  const pathname = usePathname();
  useEffect(() => {
    if (!signedIn) return;
    const pending = peekIntendedRoute();
    if (!pending) return;
    if (pathname === pending.split("?")[0]) { clearIntendedRoute(); return; }           // 도착했다
    if (pathname === "/home") { clearIntendedRoute(); router.replace(pending as Href); return; }
    if (pathname === "/" || HOLDING.test(pathname)) return;                           // 대문·로그인·온보딩 중에는 유지
    clearIntendedRoute();                                                              // 다른 화면으로 옮겨 갔으면 잊는다
  }, [signedIn, pathname, router]);
  return null;
}

/**
 * 온보딩 초안 보존 (F022·F104). 온보딩·자가진단 화면에 로그인 상태로 들어오면 한 번:
 *  1) 저장해 둔 초안(새로고침·앱 종료 전 입력)을 되살리고
 *  2) 기존 프로필을 draft.original 로 불러온 뒤, 사용자가 실제로 바꾼 항목만 그 위에 얹는다
 * 그래서 새로고침·딥링크 뒤 '추천 받기'를 눌러도 손대지 않은 저장값이 빈 값으로 덮어써지지 않는다.
 * 이후 초안이 바뀔 때마다 저장하고, reset(완료·로그아웃)이면 저장분도 지운다.
 */
const EDITING = /^\/(onboarding|diagnosis)\//;
const profileOf = (p: ProfileOut): Profile => ({ gender: p.gender, birth_year: p.birth_year ?? null, height_cm: p.height_cm ?? null,
  pc_season: p.pc_season ?? null, pc_subtone: p.pc_subtone ?? null, body_type: p.body_type ?? null, mbti: p.mbti ?? null });
function OnboardingKeeper({ signedIn }: { signedIn: boolean }) {
  const { draft, dispatch } = useOnboarding();
  const pathname = usePathname();
  const latest = useRef(draft);
  latest.current = draft;
  const [restored, setRestored] = useState(false);
  const editing = EDITING.test(pathname);
  useEffect(() => {
    if (!signedIn) { setRestored(false); return; }
    if (restored || !editing) return;
    let active = true;
    (async () => {
      const stored = await readDraft();
      if (!active) return;
      const current = latest.current;
      if (current.original) { setRestored(true); return; }                           // 설정에서 '수정'으로 들어온 경우 이미 불러왔다
      const pristine = sameProfile(current.profile, initialDraft.profile);
      const base = pristine && stored ? stored : current;                             // 사용자가 입력하던 값
      let original = base.original;
      if (!original) {
        try { const server = await api.getProfile(); if (server.profile_exists) original = profileOf(server); }
        catch { /* 프로필을 못 읽으면 입력값만 유지한다 */ }
        if (!active) return;
      }
      // 저장값과 다른 항목 = 사용자가 바꾼 것. 불러오는 동안 새로 입력한 값이 있으면 그것이 우선
      const typed = { ...touchedFields(base.profile, base.original ?? initialDraft.profile), ...touchedFields(latest.current.profile, initialDraft.profile) };
      if (original) dispatch({ type: "load", profile: { ...original, profile_exists: true, saju_enabled: false } as ProfileOut });
      if (Object.keys(typed).length) dispatch({ type: "profile", patch: typed });
      setRestored(true);
    })();
    return () => { active = false; };
  }, [signedIn, editing, restored, dispatch]);
  useEffect(() => {
    if (!restored) return;
    void writeDraft(draft === initialDraft || (draft.original === null && sameProfile(draft.profile, initialDraft.profile)) ? null : { profile: draft.profile, original: draft.original });
  }, [draft, restored]);
  return null;
}

function DemoBanner() {
  return (
    <View style={{ backgroundColor: colors.secondarySoft, paddingVertical: 5, paddingHorizontal: 12 }}>
      <Text style={{ color: colors.secondaryInk, fontFamily: fonts.medium, fontSize: 10, textAlign: "center", letterSpacing: 0.5 }}>
        LIT A&D · 포토스팟 베타
      </Text>
    </View>
  );
}
