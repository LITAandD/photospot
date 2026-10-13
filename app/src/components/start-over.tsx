import React, { useRef, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { api } from "@/api";
import { ErrorBox } from "@/components/ui";
import { errorMessage } from "@/hooks";
import { useOnboarding } from "@/state/onboarding";
import { signOutTo, takeSignOutRoute } from "@/state/sign-out";
import { colors, fonts } from "@/theme";

/** Clear recommendation inputs before the session listener returns to the landing page. */
export function StartOver() {
  const { dispatch } = useOnboarding();
  const pending = useRef(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const reset = async () => {
    if (pending.current) return;
    pending.current = true;
    setBusy(true); setError(null);
    try {
      await api.resetProfile();
      dispatch({ type: "reset" });
      signOutTo("/");
      try { await api.auth.logout(); }
      finally { takeSignOutRoute(); }
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      pending.current = false;
      setBusy(false);
    }
  };
  return <View style={{ gap: 8 }}>
    <Pressable onPress={reset} disabled={busy} accessibilityRole="button" accessibilityLabel="처음으로"
      accessibilityHint="입력한 프로필과 사주 정보를 모두 초기화하고 메인 대문으로 이동합니다"
      accessibilityState={{ disabled: busy, busy }}
      style={{ alignSelf: "flex-start", minHeight: 44, minWidth: 88, flexDirection: "row", alignItems: "center", gap: 8 }}>
      {busy ? <ActivityIndicator size="small" color={colors.ink} /> : null}
      <Text style={{ fontFamily: fonts.semibold, fontSize: 14, color: colors.ink }}>처음으로</Text>
    </Pressable>
    {error ? <ErrorBox message={error} onRetry={reset} /> : null}
  </View>;
}
