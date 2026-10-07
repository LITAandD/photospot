import React, { useCallback, useState } from "react";
import { useFocusEffect, useRouter } from "expo-router";
import { ActivityIndicator, View } from "react-native";
import { api, DEMO } from "@/api";
import { deleteAccountWithProvider, LoginCancelled } from "@/auth/providers";
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { errorMessage, useAsync } from "@/hooks";
import { useOnboarding } from "@/state/onboarding";
import { ProfileSummary } from "@/components/profile-summary";
import { SajuSummary } from "@/components/shoot-plan";

export default function Settings() {
  const router = useRouter();
  const { dispatch } = useOnboarding();
  const profile = useAsync(() => api.getProfile(), []);
  const session = useAsync(() => api.session(), []);
  useFocusEffect(useCallback(() => { profile.reload(); }, [profile.reload]));
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [confirmDelete, setConfirmDelete] = useState(false);
  const action = async (fn: () => Promise<unknown>) => {
    if (busy) return;
    setBusy(true); setError(null);
    try { await fn(); } catch (e) { if (!(e instanceof LoginCancelled)) setError(errorMessage(e)); } finally { setBusy(false); }
  };
  const edit = () => {
    if (!profile.data) return;
    dispatch({ type: "load", profile: profile.data });
    router.push("/onboarding/basic");
  };
  return <Screen style={{ paddingTop: 24 }}>
    <Title>내 정보 · 설정</Title>
    <Muted>선택한 정보를 수정하거나 언제든 삭제할 수 있어요.</Muted>
    {profile.loading ? <ActivityIndicator /> : null}
    {profile.error ? <ErrorBox message={errorMessage(profile.error)} onRetry={profile.reload} /> : null}
    {error ? <ErrorBox message={error} /> : null}
    {profile.data ? <ProfileSummary profile={profile.data} /> : null}
    <Button title="프로필 수정하기" onPress={edit} disabled={!profile.data || busy} />
    <Button title="나의 포토 타입 보기" variant="outline" onPress={() => router.push("/result")} />
    <Card style={{ gap: 12 }}>
      <Body>계정 · 포토스팟과 함께하기</Body>
      <Button title="SNS 계정 연결" variant="outline" onPress={() => router.push('/accounts')} />
      <Button title="개발자 후원 · 포토스팟 Plus" variant="outline" onPress={() => router.push('/support')} />
      <Button title="의견 보내기 · 내 피드백" variant="outline" onPress={() => router.push('/feedback')} />
      {session.data?.is_admin ? <Button title={DEMO?'운영 관리 미리보기':'운영 관리'} variant="outline" onPress={() => router.push('/admin')} /> : null}
    </Card>
    {profile.data?.saju_enabled ? <Card style={{ gap: 12 }}>
      <SajuSummary profile={profile.data} />
      <Muted>촬영 날짜를 정할 때 오행·일진 추천을 켜면 반영해요.</Muted>
      <Button title="사주 정보 삭제 및 동의 철회" variant="outline" loading={busy} onPress={() => action(async () => { await api.deleteSaju(); profile.reload(); })} />
    </Card> : null}
    <Button title="내 사진 삭제 및 분석 동의 철회" variant="outline" loading={busy} onPress={() => action(async () => { await api.revokeConsent("photo_analysis"); setError("업로드 사진을 삭제하고 분석 동의를 철회했어요."); })} />
    <Button title="개인정보 및 서비스 안내" variant="outline" onPress={() => router.push("/privacy")} />
    <Button title="로그아웃" variant="outline" disabled={busy} onPress={() => action(async () => { await api.auth.logout(); dispatch({ type: "reset" }); router.replace("/login"); })} />
    {confirmDelete ? <Card style={{ gap: 12 }}>
      <Body>계정을 삭제할까요?</Body>
      <Muted>프로필, 오행, 저장한 장소, 후기와 업로드한 사진이 삭제돼요. 되돌릴 수 없어요.</Muted>
      <Muted>유료 구독은 탈퇴로 취소되지 않아요. 먼저 후원·Plus 화면에서 스토어 구독을 관리해 주세요.</Muted>
      <Button title="계정과 개인정보 영구 삭제" loading={busy} onPress={() => action(async () => { await deleteAccountWithProvider(); dispatch({ type: "reset" }); router.replace("/"); })} />
      <Button title="취소" variant="outline" disabled={busy} onPress={() => setConfirmDelete(false)} />
    </Card> : <Button title="회원 탈퇴" variant="outline" disabled={busy} onPress={() => setConfirmDelete(true)} />}
    <View style={{ flex: 1 }} />
    <Button title="추천으로 돌아가기" variant="outline" onPress={() => router.replace("/home")} />
  </Screen>;
}
