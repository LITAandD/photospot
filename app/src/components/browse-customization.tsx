import React, { useState } from 'react';
import { useRouter } from 'expo-router';
import { View } from 'react-native';
import { api, DEMO } from '@/api';
import { beginBrowseCustomization, browseHref, clearBrowseCustomization, pendingBrowse, type BrowseContext } from '@/browse-context';
import { useOnboarding } from '@/state/onboarding';
import { Button, ErrorBox, Muted } from './ui';
import { errorMessage } from '@/hooks';

export function BrowseCustomize({ context }: { context: BrowseContext }) {
  const router = useRouter();
  const { dispatch } = useOnboarding();
  const [busy, setBusy] = useState(false), [error, setError] = useState<string | null>(null);
  const start = async () => {
    if (busy) return;
    setBusy(true); setError(null);
    try {
      const signedIn = await api.auth.isSignedIn();
      const profile = signedIn ? await api.getProfile() : null;
      beginBrowseCustomization(context);
      if (profile) { dispatch({ type: 'load', profile }); router.push('/onboarding/basic'); }
      else router.push('/login');
    } catch (e) { setError(errorMessage(e)); } finally { setBusy(false); }
  };
  return <View style={{ gap: 8 }}>
    <Muted size={12}>맞춤 설정은 선택이에요. 도시·촬영일과 보던 장소를 이어서 볼 수 있어요. 필수 동의와 만 14세 이상 확인은 그대로 적용돼요.</Muted>
    <Button title="이 조건으로 맞춤 추천 설정" onPress={() => { void start(); }} loading={busy} />
    {error ? <ErrorBox message={error} /> : null}
  </View>;
}

export function BrowseReturn() {
  const router = useRouter();
  const [context] = useState(() => DEMO ? pendingBrowse() : null);
  if (!context) return null;
  return <Button title="설정 중단하고 보던 장소로 돌아가기" variant="outline" onPress={() => {
    clearBrowseCustomization(true); router.dismissTo(browseHref(context));
  }} />;
}
