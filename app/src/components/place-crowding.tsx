import React, { useEffect, useState } from 'react';
import type { CrowdSources, AreaObservation as Reading, ForecastDay } from '@photospot/client';
import { AppState } from 'react-native';
import { apiBaseUrl, DEMO, today } from '@/api';
import { Body, Card, Muted } from './ui';

const base = (DEMO ? process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? '' : apiBaseUrl).replace(/\/$/, '');
const prefix = base + (DEMO ? '/preview' : '/v1') + '/crowding';
const fiveMinutes = 300_000;

// Each indicator refreshes independently. No account, location, or profile is sent.
function usePublicData<T>(path: string, refresh = false) {
  const [value, setValue] = useState<T | null>(null);
  useEffect(() => {
    let active = true;
    let pending: AbortController | null = null;
    async function read() {
      if (pending) return;
      const controller = new AbortController();
      pending = controller;
      const timer = setTimeout(() => controller.abort(), 8000);
      try {
        const response = await fetch(prefix + path, { credentials: 'omit', signal: controller.signal });
        const next = response.ok ? await response.json() as T : null;
        if (active) setValue(next);
      } catch { if (active) setValue(null); }
      finally { clearTimeout(timer); pending = null; }
    }
    void read();
    const interval = refresh ? setInterval(read, fiveMinutes) : undefined;
    const sub = refresh ? AppState.addEventListener('change', s => { if (s === 'active') void read(); }) : undefined;
    return () => { active = false; pending?.abort(); clearInterval(interval); sub?.remove(); };
  }, [path, refresh]);
  return value;
}

function AreaObservation({ area }: { area: string }) {
  const observation = usePublicData<Reading>('/areas/' + encodeURIComponent(area), true);
  const [, redraw] = useState(0);
  useEffect(() => {
    if (!observation) return;
    const remaining = Date.parse(observation.expires_at) - Date.now();
    if (remaining <= 0) return;
    const timer = setTimeout(() => redraw(n => n + 1), remaining + 1);
    const sub = AppState.addEventListener('change', () => redraw(n => n + 1));
    return () => { clearTimeout(timer); sub.remove(); };
  }, [observation]);
  if (!observation || !(Date.now() < Date.parse(observation.expires_at))) return null;
  const [day, time] = observation.observed_at.split('T');
  const stamp = (day === today() ? '' : day.slice(5) + ' ') + time.slice(0, 5);
  return <Card testID="area-observation" style={{ gap: 6 }}>
    <Body>주변 혼잡도 · {stamp} 관측</Body>
    <Body size={15}>{observation.area_name} 일대 · {observation.level}</Body>
    <Muted size={12}>서울시 실시간 인구 · 한국시간 기준</Muted>
    <Muted size={12}>구역 전체의 인구 밀집 정도예요. 매장 내부 인원이나 대기 시간은 알 수 없어요.</Muted>
  </Card>;
}

function shortDate(iso: string) {
  const d = new Date(iso + 'T00:00:00Z');
  return `${d.getUTCMonth() + 1}월 ${d.getUTCDate()}일(${'일월화수목금토'[d.getUTCDay()]})`;
}

function VisitForecast({ placeId, visitDate }: { placeId: string; visitDate: string }) {
  const days = usePublicData<ForecastDay[]>('/places/' + encodeURIComponent(placeId) + '/forecast', true);
  const current = today();
  const available = days?.filter(day => day.date >= current);
  const selected = available?.find(day => day.date === visitDate);
  if (!selected) return null;
  // Compare with the nearest other returned date. The feed is chronologically sorted.
  const other = available?.filter(day => day.date !== visitDate).sort((a, b) =>
    Math.abs(Date.parse(a.date) - Date.parse(visitDate)) - Math.abs(Date.parse(b.date) - Date.parse(visitDate)))[0];
  const comparison = other && (selected.index === other.index ? '비슷하게 붐빌 전망이에요.'
    : selected.index < other.index ? '선택일이 덜 붐빌 전망이에요.' : '선택일이 더 붐빌 전망이에요.');
  return <Card testID="visit-forecast" style={{ gap: 6 }}>
    <Body>방문일별 붐빔 전망</Body>
    <Body size={15}>{shortDate(visitDate)} · 예상 집중률 지수 {selected.index}</Body>
    {other ? <Muted>{shortDate(other.date)}와 비교하면 {comparison}</Muted> : null}
    <Muted size={12}>한국관광공사 관광지 집중률 · 이 관광지의 가장 붐비는 시기를 100으로 본 날짜별 상대 지수예요.</Muted>
  </Card>;
}

export function PlaceCrowding({ placeId, visitDate }: { placeId: string; visitDate: string }) {
  const sources = usePublicData<CrowdSources>('/places/' + encodeURIComponent(placeId));
  return <>
    {sources?.area ? <AreaObservation key={sources.area} area={sources.area} /> : null}
    {sources?.forecast ? <VisitForecast key={placeId} placeId={placeId} visitDate={visitDate} /> : null}
  </>;
}
