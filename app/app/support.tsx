import React, { useState } from 'react';
import { Linking } from 'react-native';
import { useRouter } from 'expo-router';
import { api, DEMO } from '@/api';
import { buyPackage, restorePurchases, storeAvailable, storePackages, type StorePackage } from '@/billing';
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from '@/components/ui';
import { errorMessage, useAsync } from '@/hooks';

const periodLabel=(value:string|null)=>({P1W:'1주',P1M:'1개월',P3M:'3개월',P6M:'6개월',P1Y:'1년'}[value??''] ?? value ?? '스토어 표시 기간');

export default function Support() {
  const router=useRouter();
  const data=useAsync(async()=>({billing:await api.billing(), packages:storeAvailable ? await storePackages() : {tips:[],plus:[]}}),[]);
  const [busy,setBusy]=useState(false),[message,setMessage]=useState<string|null>(null),[error,setError]=useState<string|null>(null);
  const run=async(fn:()=>Promise<unknown>,success:string)=>{if(busy)return;setBusy(true);setError(null);setMessage(null);try{await fn();setMessage(success);data.reload();}catch(e){if(!(e as {userCancelled?:boolean}).userCancelled)setError(errorMessage(e));}finally{setBusy(false);}};
  const buy=(p:StorePackage)=>run(()=>buyPackage(p),'스토어 구매가 완료됐어요. 구독 권한은 서버 확인 결과에 따라 반영돼요. 후원해 주셔서 감사합니다.');
  return <Screen style={{paddingTop:24}}><Title>포토스팟을 함께 키워요</Title><Muted>후원으로 개발을 응원하거나 Plus로 원하는 장소를 더 빠르게 찾아보세요.</Muted>
    {data.error?<ErrorBox message={errorMessage(data.error)} onRetry={data.reload}/>:null}{error?<ErrorBox message={error}/>:null}{message?<Card><Body>{message}</Body></Card>:null}
    <Card><Body>개발자에게 후원하기</Body><Muted>원할 때 한 번 보내는 후원이에요. 자동 갱신과 추가 기능은 없으며 기본 추천 결과에 영향을 주지 않아요.</Muted>
      {data.data?.packages.tips.map(p=><Button key={p.identifier} title={`${p.product.title} · ${p.product.priceString} / 1회`} disabled={busy} onPress={()=>buy(p)}/>)}
      {!data.data?.packages.tips.length?<Muted>현재 후원 상품을 준비 중이에요.</Muted>:null}
    </Card>
    <Card><Body>포토스팟 Plus {data.data?.billing.premium?'· 이용 중':''}</Body><Muted>배너·제휴 광고 숨기기, 사진 있는 장소만 보기, 최소 정합도 필터를 제공해요. 기본 추천은 계속 무료로 이용할 수 있어요.</Muted>
      {data.data?.packages.plus.map(p=><Button key={p.identifier} title={`${p.product.title} · ${p.product.priceString} / ${periodLabel(p.product.subscriptionPeriod)}`} disabled={busy || data.data?.billing.premium} onPress={()=>buy(p)}/>)}
      {!data.data?.packages.plus.length?<Muted>현재 구독 상품을 준비 중이에요.</Muted>:null}
      <Muted size={12}>구독은 스토어에 표시된 가격·기간으로 자동 갱신돼요. 취소는 해당 스토어의 구독 관리에서 할 수 있어요. 계정 삭제만으로 구독이 취소되지는 않아요. 환불은 결제한 스토어의 절차를 따라요.</Muted>
      {data.data?.billing.management_url?<Button title="구독 관리" variant="outline" disabled={busy} onPress={()=>run(()=>Linking.openURL(data.data!.billing.management_url!),'스토어의 구독 관리를 열었어요.')}/>:null}
    </Card>
    {!storeAvailable?<Muted>{DEMO?'체험 모드에서는 결제가 발생하지 않아요.':'후원·구독 결제는 설치형 Android·iOS 앱에서 이용할 수 있어요.'}</Muted>:null}
    <Button title="구매 복원" variant="outline" disabled={busy || !storeAvailable} onPress={()=>run(restorePurchases,'스토어 구매 내역을 다시 확인했어요. 일회성 후원은 구독 권한으로 복원되지 않아요.')}/>
    <Button title="구매 상태 다시 확인" variant="outline" disabled={busy || !data.data?.billing.configured} onPress={()=>run(()=>api.syncBilling(),'구매 상태를 확인했어요.')}/>
    <Button title="이용약관·개인정보 안내" variant="outline" onPress={()=>router.push('/privacy')}/><Button title="돌아가기" variant="outline" onPress={()=>router.replace('/settings')}/>
  </Screen>;
}
