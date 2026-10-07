import React, { useCallback, useState } from 'react';
import { Linking, Platform } from 'react-native';
import { useFocusEffect, useRouter } from 'expo-router';
import { api, DEMO } from '@/api';
import { PROVIDERS, linkWithProvider, unlinkWithProvider, LoginCancelled, type ProviderId } from '@/auth/providers';
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { useAsync, errorMessage } from '@/hooks';

const labels: Record<ProviderId,string> = { google:'Google', apple:'Apple', naver:'네이버', kakao:'카카오' };
export default function Accounts() {
  const router = useRouter();
  const data = useAsync(async () => ({ session: await api.session(), identities: await api.identities(), providers: await api.authProviders(), instagram: await api.instagram() }), []);
  useFocusEffect(useCallback(() => { data.reload(); }, [data.reload]));
  const [busy,setBusy] = useState(false), [error,setError] = useState<string|null>(null);
  const run = async (fn:()=>Promise<unknown>) => { if(busy) return; setBusy(true); setError(null); try { await fn(); data.reload(); } catch(e) { if(!(e instanceof LoginCancelled)) setError(errorMessage(e)); } finally { setBusy(false); } };
  return <Screen style={{paddingTop:24}}><Title>연결된 계정</Title><Muted>다른 로그인 수단을 연결해도 내 프로필과 저장 목록은 같은 계정에 남아요.</Muted>
    {DEMO ? <Card><Body>브라우저 체험 모드</Body><Muted>실제 SNS 인증과 계정 연결은 설치형 앱에서 확인할 수 있어요.</Muted></Card> : null}
    {data.error ? <ErrorBox message={errorMessage(data.error)} onRetry={data.reload}/> : null}{error ? <ErrorBox message={error}/> : null}
    {Object.entries(labels).map(([id,label]) => {
      const provider = id as ProviderId;
      const linked = data.data?.identities.find(x=>x.provider===provider);
      const available = !DEMO && PROVIDERS.some(x=>x.id===provider) && data.data?.providers.providers.includes(provider);
      return <Card key={id}><Body>{label} · {linked ? '연결됨' : '연결 안 됨'}</Body>
        {linked ? <Muted>{linked.display_name || linked.email || label+' 계정'}</Muted> : null}
        {linked ? <Button title="연결 해제" variant="outline" disabled={busy || (data.data?.identities.length ?? 0)<=1} onPress={()=>run(()=>unlinkWithProvider(provider))}/> :
        <Button title={available ? label+' 계정 연결' : Platform.OS==='web' ? '설치형 앱에서 연결' : '연결 준비 중'} variant="outline" disabled={!available || busy} onPress={()=>run(()=>linkWithProvider(provider))}/>}
      </Card>;
    })}
    <Muted size={12}>마지막 로그인 수단은 해제할 수 없어요.</Muted>
    <Card><Body>Instagram</Body><Muted>비즈니스·크리에이터 계정을 연결해 프로필을 확인해요. 앱 로그인 수단으로는 사용하지 않아요. 사진·피드를 게시하지 않아요.</Muted>
      {data.data?.instagram ? <><Body>@{data.data.instagram.username} · 확인 완료</Body><Button title="Instagram 연결 해제" variant="outline" disabled={busy} onPress={()=>run(()=>api.disconnectInstagram())}/><Muted size={12}>포토스팟의 연결 정보를 삭제해요. Instagram의 앱 및 웹사이트 설정에서도 접근 권한을 해제할 수 있어요.</Muted></> :
        <Button title={data.data?.session.instagram_configured ? 'Instagram 연결하기' : 'Instagram 연결 준비 중'} disabled={busy || !data.data?.session.instagram_configured || DEMO} onPress={()=>run(async()=>{const result=await api.connectInstagram(); await Linking.openURL(result.url);})}/>}
      <Button title="연결 상태 새로고침" variant="outline" disabled={busy} onPress={data.reload}/>
    </Card><Button title="설정으로 돌아가기" variant="outline" onPress={()=>router.replace('/settings')}/>
  </Screen>;
}
