import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { today } from "@/api";
import { calendarMonth, moveCalendarMonth, validCalendarDate } from "@/calendar";
import { Body, Button, Label, Muted } from "./ui";
import { colors, fonts } from "@/theme";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];
type Month = { year: number; month: number };
const monthOf = (date: string): Month => ({ year: Number(date.slice(0, 4)), month: Number(date.slice(5, 7)) - 1 });
const ordinal = (m: Month) => m.year * 12 + m.month;
/** 촬영일은 오늘 이후만 고를 수 있다 (S-4): 지난 날짜는 비활성, 이번 달 이전으로는 넘어가지 않는다 */
export function CalendarField({ value, onChange, disabled = false }: {
  value: string; onChange: (value: string) => void; disabled?: boolean;
}) {
  const min = today();
  const selected = validCalendarDate(value) ? value : min;
  const firstMonth = monthOf(min);
  const startMonth = () => { const m = monthOf(selected); return ordinal(m) < ordinal(firstMonth) ? firstMonth : m; };
  const [open, setOpen] = useState(false);
  const [view, setView] = useState<Month>(startMonth);
  const toggle = () => {
    if (!open) setView(startMonth());
    setOpen(!open);
  };
  const pick = (date: string) => { if (date < min) return; onChange(date); setOpen(false); };
  const atFirstMonth = ordinal(view) <= ordinal(firstMonth);
  const weekday = WEEKDAYS[new Date(`${selected}T12:00:00Z`).getUTCDay()];
  // react-native-web 0.21은 accessibilityState를 DOM에 옮기지 않아 aria-* 를 함께 넘긴다
  return <View style={{ gap: 8 }}>
    <Label>촬영일</Label>
    <Pressable accessibilityRole="button" accessibilityLabel="촬영일 달력 열기" aria-expanded={open} accessibilityState={{ expanded: open, disabled }} disabled={disabled} onPress={toggle} style={s.field}>
      <Body>{selected.replace(/-/g, ".")} ({weekday})</Body><Muted size={13}>{open ? "달력 닫기" : "달력에서 선택"}</Muted>
    </Pressable>
    {open && !disabled ? <View testID="shoot-date-calendar" style={s.calendar}>
      <View style={s.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="이전 달" disabled={atFirstMonth} accessibilityState={{ disabled: atFirstMonth }}
          onPress={() => setView(moveCalendarMonth(view.year, view.month, -1))} style={[s.arrow, atFirstMonth && { opacity: 0.35 }]}><Body>‹</Body></Pressable>
        <Text testID="calendar-month" accessibilityRole="header" style={s.month}>{view.year}년 {view.month + 1}월</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="다음 달" disabled={view.year >= 9999 && view.month === 11} onPress={() => setView(moveCalendarMonth(view.year, view.month, 1))} style={s.arrow}><Body>›</Body></Pressable>
      </View>
      <View style={s.grid}>{WEEKDAYS.map((day) => <View key={day} style={s.cell}><Muted size={12}>{day}</Muted></View>)}</View>
      <View style={s.grid}>{calendarMonth(view.year, view.month).map((date, index) => {
        if (!date) return <View key={`blank-${index}`} style={s.cell} />;
        const past = date < min, on = date === selected;
        return <Pressable key={date} disabled={past}
          accessibilityRole="button" accessibilityLabel={`${Number(date.slice(0, 4))}년 ${Number(date.slice(5, 7))}월 ${Number(date.slice(8))}일${past ? ", 지난 날짜" : ""}`}
          aria-selected={on} accessibilityState={{ selected: on, disabled: past }} testID={`calendar-day-${date}`} onPress={() => pick(date)}
          style={[s.cell, date === min && s.today, on && s.selected, past && s.past]}>
          <Text style={[s.day, on && { color: colors.accentInk }, past && { color: colors.muted }]}>{Number(date.slice(8))}</Text>
        </Pressable>;
      })}</View>
      <Button title="오늘 선택" variant="outline" onPress={() => pick(min)} />
    </View> : null}
  </View>;
}
const s = StyleSheet.create({
  field: { minHeight: 54, borderWidth: 1.5, borderColor: colors.lineStrong, borderRadius: 12, padding: 12, flexDirection: "row", flexWrap: "wrap", gap: 8, justifyContent: "space-between", alignItems: "center" },
  calendar: { borderWidth: 1, borderColor: colors.line, borderRadius: 12, backgroundColor: colors.card, padding: 10, gap: 8 },
  header: { flexDirection: "row", justifyContent: "space-between", alignItems: "center" },
  arrow: { minHeight: 44, width: 44, justifyContent: "center", alignItems: "center" },
  month: { fontFamily: fonts.semibold, color: colors.ink, fontSize: 16 },
  grid: { flexDirection: "row", flexWrap: "wrap" },
  cell: { width: "14.285714%", minHeight: 44, justifyContent: "center", alignItems: "center", borderRadius: 8 },
  day: { fontFamily: fonts.body, color: colors.ink, fontSize: 14 },
  today: { borderWidth: 1, borderColor: colors.accent },
  selected: { backgroundColor: colors.accentSoft },
  past: { opacity: 0.4 },
});
