import { useRouter, type Href } from "expo-router";
import React, { useEffect, useRef, useState } from "react";

import { api, DEMO } from "@/api";
import { Linking, Pressable, StyleSheet, Text, View, useWindowDimensions } from "react-native";

import { Button, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { errorMessage } from "@/hooks";
import { colors, fonts } from "@/theme";
import { onSessionChange, takeIntendedRoute } from "@/state/auth-session";
import { BrandMark } from '@/components/brand-mark';
import { PhotoShowcase } from '@/components/photo-showcase';

export default function Welcome() {
  const router = useRouter();
  const wide = useWindowDimensions().width >= 840;
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const pending = useRef(false);
  useEffect(() => {
    let active = true, changed = false;
    const unsubscribe = onSessionChange((value) => { changed = true; if (active) setSignedIn(value); });
    api.auth.isSignedIn().then((value) => { if (active && !changed) setSignedIn(value); })
      .catch(() => { if (active && !changed) setSignedIn(false); });
    return () => { active = false; unsubscribe(); };
  }, []);
  // 프로필이 있으면 홈(또는 기억해 둔 딥링크)으로, 없으면 온보딩으로
  const enter = async () => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setError(null);
    try {
      const profile = await api.getProfile();
      router.replace(profile.profile_exists ? (takeIntendedRoute() as Href | null) ?? "/home" : "/onboarding/basic");
    } catch (e) { setError(errorMessage(e)); }
    finally { pending.current = false; setBusy(false); }
  };
  // 로그인된 사용자는 실행할 때마다 '계속하기'를 누르지 않아도 바로 들어간다 (F081). 실패하면 버튼으로 다시 시도
  useEffect(() => { if (signedIn) void enter(); }, [signedIn]);   // eslint-disable-line react-hooks/exhaustive-deps
  const start = () => { if (!signedIn) router.push("/login"); else void enter(); };
  return (
    <Screen wide style={{ paddingTop: wide ? 40 : 22, gap: wide ? 64 : 30 }}>
      <View style={s.header}><BrandMark/><Text style={s.headerNote}>나를 담는 장소</Text></View>
      <View style={[s.hero, wide && { flexDirection: 'row', alignItems: 'center', gap: 56 }]}>
        <View style={{ flex: wide ? 1 : undefined, gap: 22 }}>
          <View style={{ gap: 14 }}>
            <Text style={s.eyebrow}>FIND YOUR PHOTOSPOT</Text>
            <Title size={wide ? 48 : 36}>오늘의 나,{"\n"}어디서 찍을까.</Title>
            <Muted size={15}>나의 컬러와 취향에 어울리는 빛과 공간.{"\n"}익숙한 동네에서도 새로운 배경을 발견해요.</Muted>
          </View>
          <View style={s.features}>{['퍼스널컬러', '체형', 'MBTI'].map(label=><Text key={label} style={s.feature}>{label}</Text>)}</View>
          {wide ? <View style={s.action}>
            {error ? <ErrorBox message={error}/> : null}
            <Button title={signedIn ? '계속하기' : '시작하기'} onPress={start} disabled={signedIn === null} loading={busy}/>
            <Muted size={12}>프로필 입력은 선택이에요. 가볍게 시작해 보세요.</Muted>
          </View> : null}
        </View>
        <View style={{ flex: wide ? 1.2 : undefined }}><PhotoShowcase height={wide ? 430 : 260}/></View>
        {!wide ? <View style={s.action}>
          {error ? <ErrorBox message={error} /> : null}
          <Button title={signedIn ? "계속하기" : "시작하기"} onPress={start} disabled={signedIn === null} loading={busy} />
          <Text style={s.hint}>모든 항목은 건너뛸 수 있어요</Text>
        </View> : null}
      </View>
      {DEMO ? <Button title="도시별 장소 먼저 둘러보기" variant="outline" onPress={() => router.push("/browse")} /> : null}
      <View style={s.footer}>
        <Text style={s.footerTitle}>취향을 담고. 장소를 찾고. 나답게 찍고.</Text>
        <Muted size={12}>서울 · 부산 · 강릉에서 시작하는 나만의 사진 산책</Muted>
        <Pressable accessibilityRole="link" accessibilityLabel="LIT A&D 홈페이지" onPress={() => Linking.openURL('https://www.litaandd.com/').catch(() => setError('홈페이지를 열지 못했어요. 잠시 후 다시 시도해 주세요.'))} style={{ minHeight: 44, justifyContent: 'center' }}>
          <Text style={{ fontFamily: fonts.medium, fontSize: 12, color: colors.accentInk }}>공간을 탐색하는 새로운 시선, LIT A&D ↗</Text>
        </Pressable>
      </View>
    </Screen>
  );
}

const s = StyleSheet.create({
  header: { flexDirection: 'row', justifyContent: 'space-between', alignItems: 'center' },
  headerNote: { fontFamily: fonts.medium, fontSize: 11, color: colors.muted },
  hero: { gap: 24 },
  eyebrow: { fontFamily: fonts.semibold, color: colors.secondaryInk, fontSize: 10, letterSpacing: 2 },
  features: { flexDirection: 'row', flexWrap: 'wrap', gap: 8 },
  feature: { fontFamily: fonts.medium, fontSize: 12, color: colors.accentInk, backgroundColor: colors.accentSoft, paddingHorizontal: 12, paddingVertical: 7, borderRadius: 20 },
  action: { gap: 10 },
  hint: { textAlign: 'center', fontFamily: fonts.body, fontSize: 12, color: colors.muted },
  footer: { gap: 8, paddingVertical: 22, borderTopWidth: 1, borderTopColor: colors.line },
  footerTitle: { fontFamily: fonts.medium, fontSize: 14, color: colors.ink },
});
