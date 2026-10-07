import React, { useState } from 'react';
import { Pressable, TextInput, View } from 'react-native';
import { useRouter } from 'expo-router';
import { api, DEMO } from '@/api';
import type { AppFeedback } from '@photospot/client';
import { Body, Button, Card, Chip, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { errorMessage, useAsync } from '@/hooks';
import { colors, fonts } from '@/theme';

const kinds = {bug:'오류 제보',idea:'기능 제안',place:'장소 정보',other:'기타'} as const;
export default function Feedback() {
  const router=useRouter(), history=useAsync(()=>api.myAppFeedback(),[]);
  const [category,setCategory]=useState<AppFeedback['category']>('idea'),[message,setMessage]=useState(''),[consent,setConsent]=useState(false);
  const [busy,setBusy]=useState(false),[error,setError]=useState<string|null>(null),[sent,setSent]=useState(false);
  const send=async()=>{if(busy)return;setBusy(true);setError(null);try{await api.submitAppFeedback({category,message:message.trim(),ai_consent:consent});setMessage('');setConsent(false);setSent(true);history.reload();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}};
  const remove=async(id:string)=>{setBusy(true);try{await api.deleteAppFeedback(id);history.reload();}catch(e){setError(errorMessage(e));}finally{setBusy(false);}};
  return <Screen style={{paddingTop:24}}><Title>의견 보내기</Title><Muted>불편했던 점과 바라는 기능을 알려주세요. 개발자가 검토해 개선 순서를 정해요.</Muted>
    {DEMO?<Card><Body>이 브라우저에만 저장돼요</Body><Muted>현재 체험 모드에서는 개발자나 GPT에게 전송되지 않아요.</Muted></Card>:null}
    {sent?<Card><Body>{DEMO?'의견을 이 브라우저에 저장했어요.':'의견을 접수했어요. 감사합니다.'}</Body></Card>:null}
    <View style={{flexDirection:'row',gap:8,flexWrap:'wrap'}}>{Object.entries(kinds).map(([k,label])=><Chip key={k} label={label} selected={category===k} onPress={()=>setCategory(k as AppFeedback['category'])}/>)}</View>
    <TextInput accessibilityLabel="앱 개선 의견" multiline value={message} onChangeText={v=>{setMessage(v);setSent(false);}} maxLength={2000} placeholder="어떤 화면에서 무엇이 불편했나요? 원하는 동작도 함께 알려주세요. 이름·연락처·계정·생년월일 등 개인정보는 적지 마세요."
      style={{minHeight:160,padding:16,borderWidth:1,borderColor:colors.line,borderRadius:16,backgroundColor:colors.card,color:colors.ink,fontFamily:fonts.body,fontSize:16,textAlignVertical:'top'}}/>
    <Muted size={12}>{message.length}/2000 · 하루 5건까지</Muted>
    <Pressable accessibilityRole="checkbox" accessibilityState={{checked:consent}} onPress={()=>setConsent(!consent)}><Body>{consent?'☑':'□'} [선택] GPT를 이용한 의견 분석에 동의해요</Body></Pressable>
    <Muted size={12}>동의하면 개발자가 개인정보를 제거한 의견을 OpenAI API에 보내 요약·개선 우선순위를 만들어요. 계정·프로필·위치 정보는 함께 보내지 않아요. 동의하지 않아도 의견을 접수해요. 아래에서 삭제하면 원본과 연결된 개선안을 삭제하며 이후 분석 대상에서도 제외돼요. 이미 전송된 내용에는 제공자의 보관 정책이 적용돼요.</Muted>
    {error?<ErrorBox message={error}/>:null}<Button title="의견 보내기" loading={busy} disabled={message.trim().length<5} onPress={send}/>
    <Body>내가 보낸 의견</Body>{history.error?<ErrorBox message={errorMessage(history.error)} onRetry={history.reload}/>:null}
    {history.data?.map(f=><Card key={f.id}><Body>{kinds[f.category]} · {new Date(f.created_at).toLocaleDateString('ko-KR')}</Body><Muted>{f.message}</Muted><Muted size={12}>AI 분석 {f.ai_consent?'동의':'미동의'}</Muted><Button title="의견 삭제 · 분석 동의 철회" variant="outline" disabled={busy} onPress={()=>remove(f.id)}/></Card>)}
    <Button title="설정으로 돌아가기" variant="outline" onPress={()=>router.replace('/settings')}/>
  </Screen>;
}
