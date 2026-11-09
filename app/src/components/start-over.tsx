import React, { useRef, useState } from "react";
import { ActivityIndicator, Pressable, Text, View } from "react-native";
import { api } from "@/api";
import { Button, Card, ErrorBox, Muted, Title } from "@/components/ui";
import { errorMessage } from "@/hooks";
import { useOnboarding } from "@/state/onboarding";
import { signOutTo, takeSignOutRoute } from "@/state/sign-out";
import { colors, fonts } from "@/theme";

/**
 * 프로필·사주를 지우고 로그아웃해 대문으로 돌아간다. 한 번의 탭으로 지워지지 않게 먼저 무엇이 삭제되는지 확인 창을 연다 (F021).
 * 저장한 장소는 서버 계약대로 계정에 남는다 (DELETE /v1/me/profile) — 창에 적어 두고, 비우기는 /saved 에서 따로 한다 (S-11).
 */
export function StartOver() {
  const { dispatch } = useOnboarding();
  const pending = useRef(false);
  const [confirming, setConfirming] = useState(false);
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
  const cancel = () => { if (!busy) { setConfirming(false); setError(null); } };
  return <View style={{ gap: 8 }}>
    <Pressable onPress={() => { setError(null); setConfirming(true); }} disabled={busy} accessibilityRole="button" accessibilityLabel="처음으로"
      accessibilityHint="확인 창이 열려요. 입력한 프로필과 사주 정보를 초기화하고 로그아웃합니다. 저장한 장소는 남아요"
      aria-expanded={confirming} aria-busy={busy} accessibilityState={{ disabled: busy, busy, expanded: confirming }}
      style={{ alignSelf: "flex-start", minHeight: 44, minWidth: 88, flexDirection: "row", alignItems: "center", gap: 8 }}>
      {busy ? <ActivityIndicator size="small" color={colors.ink} /> : null}
      <Text style={{ fontFamily: fonts.semibold, fontSize: 14, color: colors.ink }}>처음으로</Text>
    </Pressable>
    {confirming ? <View testID="start-over-confirm" role="alertdialog" aria-modal accessibilityLabel="처음으로 확인">
      <Card style={{ gap: 12 }}>
        <Title size={20}>처음부터 다시 시작할까요?</Title>
        <Muted>다음 정보가 바로 삭제되고 되돌릴 수 없어요.</Muted>
        <View style={{ gap: 4 }}>
          <Muted>• 입력한 프로필(성별·출생연도·키·퍼스널컬러·체형·MBTI)과 포토 타입</Muted>
          <Muted>• 사주 정보와 사주 분석 동의</Muted>
        </View>
        <Muted>로그아웃되어 대문으로 돌아가요. 저장한 장소는 계정에 남고, 저장 목록에서 따로 비울 수 있어요.</Muted>
        {error ? <ErrorBox message={error} onRetry={reset} /> : null}
        <Button title="초기화하고 처음으로" onPress={() => { void reset(); }} loading={busy} />
        <Button title="취소" variant="outline" onPress={cancel} disabled={busy} />
      </Card>
    </View> : null}
  </View>;
}
