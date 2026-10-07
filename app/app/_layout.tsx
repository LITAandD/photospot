import { Stack, useRouter } from "expo-router";
import React, { useEffect } from "react";

import { DEMO, onSignedOut } from "@/api";
import { useAppFonts } from "@/fonts";
import { Text, View } from "react-native";
import { SafeAreaProvider } from "react-native-safe-area-context";

import { OnboardingProvider, useOnboarding } from "@/state/onboarding";
import { colors } from "@/theme";

export default function RootLayout() {
  const loaded = useAppFonts();
  if (!loaded) return null;
  return (
    <SafeAreaProvider>
      <OnboardingProvider>
        <SessionListener />
        {DEMO ? <DemoBanner /> : null}
        <Stack screenOptions={{ headerShown: false, contentStyle: { backgroundColor: colors.bg } }} />
      </OnboardingProvider>
    </SafeAreaProvider>
  );
}

function SessionListener() {
  const router = useRouter();
  const { dispatch } = useOnboarding();
  useEffect(() => onSignedOut(() => { dispatch({ type: "reset" }); router.dismissAll(); router.replace("/login"); }), [router, dispatch]);
  return null;
}

function DemoBanner() {
  return (
    <View style={{ backgroundColor: "#1F1D1A", paddingVertical: 6, paddingHorizontal: 12 }}>
      <Text style={{ color: "#F6F3EE", fontSize: 12, textAlign: "center" }}>
        웹 체험
      </Text>
    </View>
  );
}
