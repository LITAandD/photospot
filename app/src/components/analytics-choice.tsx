import React, { useEffect, useState } from 'react';
import { analyticsAllowed, setAnalyticsChoice } from '@/analytics';
import { Body, Button, Card, Muted } from '@/components/ui';

export function AnalyticsChoice() {
  const [allowed, setAllowed] = useState(false);
  useEffect(() => { void analyticsAllowed().then(setAllowed); }, []);
  return <Card style={{ gap: 10 }}>
    <Body>이용 통계 공유 · 선택</Body>
    <Muted size={12}>허용하면 방문 세션, 유입 경로와 추천·카드 노출·장소 보기·지도 열기·저장·오류 이벤트를 90일간 보관해 개선에 사용해요. 입력한 프로필·정확한 위치·의견 내용은 보내지 않아요. 지속되는 브라우저 식별자는 수집하지 않아요. 허용하지 않아도 모든 기능을 이용할 수 있어요.</Muted>
    <Button title={allowed ? '통계 공유 중 · 끄기' : '통계 공유 안 함 · 허용하기'} variant="outline"
      onPress={() => { const next = !allowed; setAllowed(next); void setAnalyticsChoice(next); }} />
  </Card>;
}
