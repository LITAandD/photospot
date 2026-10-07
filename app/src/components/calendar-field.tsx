import React, { useState } from "react";
import { Pressable, StyleSheet, Text, View } from "react-native";
import { today } from "@/api";
import { calendarMonth, moveCalendarMonth, validCalendarDate } from "@/calendar";
import { Body, Button, Label, Muted } from "./ui";
import { colors, fonts } from "@/theme";

const WEEKDAYS = ["일", "월", "화", "수", "목", "금", "토"];
export function CalendarField({ value, onChange, disabled = false }: {
  value: string; onChange: (value: string) => void; disabled?: boolean;
}) {
  const selected = validCalendarDate(value) ? value : today();
  const [open, setOpen] = useState(false);
  const [view, setView] = useState({ year: Number(selected.slice(0, 4)), month: Number(selected.slice(5, 7)) - 1 });
  const toggle = () => {
    if (!open) setView({ year: Number(selected.slice(0, 4)), month: Number(selected.slice(5, 7)) - 1 });
    setOpen(!open);
  };
  const pick = (date: string) => { onChange(date); setOpen(false); };
  const weekday = WEEKDAYS[new Date(`${selected}T12:00:00Z`).getUTCDay()];
  return <View style={{ gap: 8 }}>
    <Label>촬영일</Label>
    <Pressable accessibilityRole="button" accessibilityLabel="촬영일 달력 열기" accessibilityState={{ expanded: open, disabled }} disabled={disabled} onPress={toggle} style={s.field}>
      <Body>{selected.replace(/-/g, ".")} ({weekday})</Body><Muted size={13}>{open ? "달력 닫기" : "달력에서 선택"}</Muted>
    </Pressable>
    {open && !disabled ? <View testID="shoot-date-calendar" style={s.calendar}>
      <View style={s.header}>
        <Pressable accessibilityRole="button" accessibilityLabel="이전 달" disabled={view.year <= 1 && view.month === 0} onPress={() => setView(moveCalendarMonth(view.year, view.month, -1))} style={s.arrow}><Body>‹</Body></Pressable>
        <Text testID="calendar-month" accessibilityRole="header" style={s.month}>{view.year}년 {view.month + 1}월</Text>
        <Pressable accessibilityRole="button" accessibilityLabel="다음 달" disabled={view.year >= 9999 && view.month === 11} onPress={() => setView(moveCalendarMonth(view.year, view.month, 1))} style={s.arrow}><Body>›</Body></Pressable>
      </View>
      <View style={s.grid}>{WEEKDAYS.map((day) => <View key={day} style={s.cell}><Muted size={12}>{day}</Muted></View>)}</View>
      <View style={s.grid}>{calendarMonth(view.year, view.month).map((date, index) => date ? <Pressable key={date}
        accessibilityRole="button" accessibilityLabel={`${Number(date.slice(0, 4))}년 ${Number(date.slice(5, 7))}월 ${Number(date.slice(8))}일`}
        accessibilityState={{ selected: date === selected }} testID={`calendar-day-${date}`} onPress={() => pick(date)}
        style={[s.cell, date === today() && s.today, date === selected && s.selected]}>
        <Text style={[s.day, date === selected && { color: colors.accentInk }]}>{Number(date.slice(8))}</Text>
      </Pressable> : <View key={`blank-${index}`} style={s.cell} />)}</View>
      <Button title="오늘 선택" variant="outline" onPress={() => pick(today())} />
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
});
