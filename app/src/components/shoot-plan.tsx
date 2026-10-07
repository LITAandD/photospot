import type { ProfileOut, SajuIn } from "@photospot/client";
import React, { useEffect, useState } from "react";
import { Pressable, View } from "react-native";
import { api } from "@/api";
import { Body, Button, Card, Chip, ErrorBox, Field, Muted } from "@/components/ui";
import { errorMessage, useAsync } from "@/hooks";
import { formatBirthDate } from "@/birth-input";
import { BirthHourSelect } from "@/components/birth-hour-select";

const ELEMENTS: Record<string, string> = { wood: "목", fire: "화", earth: "토", metal: "금", water: "수" };

export function SajuSummary({ profile }: { profile: ProfileOut }) {
  if (!profile.saju_enabled) return null;
  const percents = profile.saju_percents;
  const values = Object.values(percents ?? {});
  const lowest = values.length === 5 ? Math.min(...values) : null;
  const lacking = lowest !== null && lowest < Math.max(...values) ? Object.keys(ELEMENTS).filter((e) => percents?.[e as keyof typeof percents] === lowest) : [];
  return <View style={{ gap: 6 }}>
    <Body>나의 대표 오행 · {ELEMENTS[profile.saju_element ?? ""] ?? "저장됨"}</Body>
    {profile.saju_percents ? <Muted size={13}>{Object.entries(profile.saju_percents).map(([key, value]) => `${ELEMENTS[key]} ${value}%`).join(" · ")}</Muted> : null}
    <Body>{lowest === null ? "오행 비율을 다시 계산해 주세요" : lacking.length ? `보완할 오행 · ${lacking.map((e) => ELEMENTS[e]).join("·")} (각 ${lowest}%)` : "오행 비율이 같아 특정 보완 대상이 없어요"}</Body>
  </View>;
}

export function ShootPlan({ date, revision, onApply }: {
  date: string; revision: number; onApply: (date: string) => void;
}) {
  const profile = useAsync(() => api.getProfile(), [revision]);
  const [dateText, setDateText] = useState(date);
  const [editing, setEditing] = useState(false);
  const [birth, setBirth] = useState("");
  const [time, setTime] = useState<SajuIn["birth_hour_branch"]>(null);
  const [calendar, setCalendar] = useState<"solar" | "lunar">("solar");
  const [leap, setLeap] = useState(false);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setDateText(date); }, [date]);
  useEffect(() => { if (profile.data && (!profile.data.saju_enabled || !profile.data.saju_percents)) setEditing(true); }, [profile.data]);
  const apply = async () => {
    if (busy) return;
    setError(null);
    const parsed = new Date(`${dateText}T12:00:00Z`);
    if (!/^\d{4}-\d{2}-\d{2}$/.test(dateText) || !Number.isFinite(parsed.getTime()) || parsed.toISOString().slice(0, 10) !== dateText) {
      setError("촬영일을 YYYY-MM-DD 형식의 실제 날짜로 입력해 주세요"); return;
    }
    setBusy(true);
    try {
      if (editing || !profile.data?.saju_enabled || !profile.data?.saju_percents) {
        if (!consent) throw new Error("오행을 계산하려면 생년월일시 사용에 동의해 주세요");
        if (!/^\d{4}-\d{2}-\d{2}$/.test(birth)) throw new Error("생년월일을 YYYY-MM-DD 형식으로 입력해 주세요");
        await api.putSaju({ birth_date: birth, birth_time: null, birth_hour_branch: time, calendar, leap_month: leap, consent: true });
        setBirth(""); setTime(null); setConsent(false); setEditing(false);
        profile.reload();
      }
      onApply(dateText);
    } catch (e) { setError(errorMessage(e)); }
    finally { setBusy(false); }
  };
  return <Card style={{ gap: 12 }}>
    <Body>촬영 날짜와 사주 정보</Body>
    <Field label="촬영일" value={dateText} onChange={setDateText} placeholder="YYYY-MM-DD" />
    {profile.error ? <ErrorBox message={errorMessage(profile.error)} onRetry={profile.reload} /> : null}
    {profile.data?.saju_enabled ? <>
      <SajuSummary profile={profile.data} />
      <Button title={editing ? "저장된 오행 사용" : "생년월일로 다시 계산"} variant="outline" disabled={busy} onPress={() => { setEditing(!editing); setBirth(""); setTime(null); setConsent(false); }} />
    </> : null}
    {(editing || !profile.data?.saju_enabled || !profile.data?.saju_percents) ? <View style={{ gap: 10 }}>
      <Field label="생년월일" value={birth} onChange={(value) => setBirth(formatBirthDate(value))} placeholder="예: 19930821 → 1993-08-21" keyboard="numeric" />
      <BirthHourSelect value={time} onChange={setTime} disabled={busy} />
      <Muted size={12}>끝 시각은 다음 구간이에요. 모름은 시주 없이, 자시는 입력한 생일의 일주로 계산해요. 12지시 선택은 두 시간 구간의 근사값으로 절기 경계의 정확한 출생 시각까지 구분하지는 않아요.</Muted>
      <View style={{ flexDirection: "row", gap: 8 }}>
        {(["solar", "lunar"] as const).map((c) => <Chip key={c} label={c === "solar" ? "양력" : "음력"} selected={calendar === c} onPress={() => { setCalendar(c); setLeap(false); }} />)}
      </View>
      {calendar === "lunar" ? <Pressable accessibilityRole="checkbox" accessibilityLabel="음력 윤달" accessibilityState={{ checked: leap }} onPress={() => setLeap(!leap)}><Body>{leap ? "☑" : "□"} 음력 윤달이에요</Body></Pressable> : null}
      <Pressable accessibilityRole="checkbox" accessibilityLabel="오행 계산 동의" aria-checked={consent} accessibilityState={{ checked: consent }} onPress={() => { setConsent(!consent); setError(null); }}>
        <Muted size={13}>{consent ? "☑" : "□"} 생년월일시로 오행을 계산하는 데 동의해요. 원본은 저장하지 않고 오행 비율만 보관해요.</Muted>
      </Pressable>
    </View> : null}
    <Muted size={12}>비율이 가장 낮은 오행을 가진 장소를 찾고 촬영일의 일진을 보조 반영해요. 동률은 함께 반영해요. 취향 탐색용이며 운세나 길흉을 판단하지 않아요.</Muted>
    {error ? <ErrorBox message={error} /> : null}
    <Button title="오행·일진 장소 추천 보기" onPress={apply} loading={busy} disabled={profile.loading || !!profile.error} />
  </Card>;
}
