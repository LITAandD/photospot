import { Stack, useRouter } from "expo-router";
import React, { useEffect, useState } from "react";

import { api, DEMO, onSignedOut } from "@/api";
import { onSessionChange } from '@/state/auth-session';
import { useAppFonts } from "@/fonts";
import { Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { OnboardingProvider, useOnboarding } from "@/state/onboarding";
import { takeSignOutRoute } from "@/state/sign-out";
import { colors, fonts } from "@/theme";

export default function RootLayout() {
  const loaded = useAppFonts();
  const [signedIn, setSignedIn] = useState<boolean | null>(null);
  useEffect(() => {
    let active = true, changed = false;
    const unsubscribe = onSessionChange(value => { changed = true; if (active) setSignedIn(value); });
    api.auth.isSignedIn().then(value => { if (active && !changed) setSignedIn(value); })
      .catch(() => { if (active && !changed) setSignedIn(false); });
    return () => { active = false; unsubscribe(); };
  }, []);
  // Protected screens cannot start GPS/requests before checking the session.
  if (!loaded || signedIn === null) return null;
  return (
    <SafeAreaProvider>
      <OnboardingProvider>
        <SessionListener />
        {DEMO ? <DemoBanner /> : null}
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }}>
          <Stack.Screen name="login" />
          <Stack.Screen name="index" />
          <Stack.Screen name="privacy" />
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

function SessionListener() {
  const router = useRouter();
  const { dispatch } = useOnboarding();
  useEffect(() => onSignedOut(() => { dispatch({ type: "reset" }); router.replace(takeSignOutRoute()); }), [router, dispatch]);
  return null;
}

function DemoBanner() {
  return (
    <View style={{ backgroundColor: "#1F1D1A", paddingVertical: 6, paddingHorizontal: 12 }}>
      <Text style={{ color: "#F6F3EE", fontFamily: fonts.body, fontSize: 12, textAlign: "center" }}>
        웹 체험
      </Text>
    </View>
  );
}
