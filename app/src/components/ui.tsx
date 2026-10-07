import { Link, useRouter } from "expo-router";
import React from "react";
import { ActivityIndicator, Pressable, ScrollView, StyleSheet, Text, TextInput, View, type ViewStyle } from "react-native";
import { SafeAreaView } from "react-native-safe-area-context";

import { colors, fonts, radius } from "@/theme";

export function Screen({ children, scroll = true, style }: { children: React.ReactNode; scroll?: boolean; style?: ViewStyle }) {
  const body = <View style={[s.body, style]}>{children}</View>;
  return (
    <SafeAreaView style={s.safe} edges={["top", "bottom"]}>
      {scroll ? <ScrollView contentContainerStyle={s.scroll} keyboardShouldPersistTaps="handled">{body}</ScrollView> : body}
    </SafeAreaView>
  );
}

export function Title({ children, size = 28 }: { children: React.ReactNode; size?: number }) {
  return <Text style={[s.title, { fontSize: size, lineHeight: size * 1.35 }]}>{children}</Text>;
}
export const Muted = ({ children, size = 14 }: { children: React.ReactNode; size?: number }) => (
  <Text style={{ fontFamily: fonts.body, fontSize: size, lineHeight: size * 1.6, color: colors.muted }}>{children}</Text>
);
export const Label = ({ children }: { children: React.ReactNode }) => <Text style={s.label}>{children}</Text>;
export const Body = ({ children, size = 15 }: { children: React.ReactNode; size?: number }) => (
  <Text style={{ fontFamily: fonts.body, fontSize: size, lineHeight: size * 1.55, color: colors.ink }}>{children}</Text>
);

export function Button({ title, onPress, variant = "primary", disabled, loading }:
  { title: string; onPress: () => void; variant?: "primary" | "outline"; disabled?: boolean; loading?: boolean }) {
  const primary = variant === "primary";
  return (
    <Pressable onPress={onPress} disabled={disabled || loading} accessibilityRole="button"
      accessibilityState={{ disabled: !!(disabled || loading), busy: !!loading }}
      style={({ pressed }) => [s.button, primary ? s.buttonPrimary : s.buttonOutline, (disabled || pressed) && { opacity: 0.6 }]}>
      {loading ? <ActivityIndicator color={primary ? "#fff" : colors.ink} /> :
        <Text style={[s.buttonText, { color: primary ? "#fff" : colors.ink }]}>{title}</Text>}
    </Pressable>
  );
}

export function Chip({ label, selected, onPress, role = "button" }: { label: string; selected: boolean; onPress: () => void; role?: "button" | "radio" }) {
  return (
    <Pressable onPress={onPress} accessibilityRole={role} aria-checked={role === "radio" ? selected : undefined} accessibilityState={role === "radio" ? { checked: selected } : { selected }}
      style={[s.chip, selected && s.selected]}>
      <Text style={[s.chipText, selected && { color: colors.accentInk }]}>{label}</Text>
    </Pressable>
  );
}

/** 왼쪽 제목 + 오른쪽 설명이 있는 선택 카드 (성별·체형·MBTI 등) */
export function OptionRow({ title, desc, selected, onPress, swatch }:
  { title: string; desc?: string; selected: boolean; onPress: () => void; swatch?: string }) {
  return (
    <Pressable onPress={onPress} accessibilityRole="button" accessibilityState={{ selected }}
      style={[s.option, selected && s.selected]}>
      {swatch ? <View style={[s.swatch, { backgroundColor: swatch }]} /> : null}
      {swatch ? <View style={{ flex: 1, gap: 4 }}>
        <Text style={[s.optionTitle, selected && { color: colors.accentInk }]}>{title}</Text>
        {desc ? <Text style={[s.optionDesc, { textAlign: "left", flex: 0, fontSize: 12 }]}>{desc}</Text> : null}
      </View> : <><Text style={[s.optionTitle, selected && { color: colors.accentInk }]}>{title}</Text>
        {desc ? <Text style={s.optionDesc}>{desc}</Text> : null}</>}
    </Pressable>
  );
}

export function Field({ label, value, onChange, placeholder, suffix, keyboard = "default" }:
  { label: string; value: string; onChange: (v: string) => void; placeholder?: string; suffix?: string; keyboard?: "default" | "numeric" }) {
  return (
    <View style={{ gap: 8 }}>
      <Label>{label}</Label>
      <View style={s.field}>
        <TextInput value={value} onChangeText={onChange} placeholder={placeholder} keyboardType={keyboard}
          placeholderTextColor={colors.muted} style={s.fieldInput} accessibilityLabel={label} />
        {suffix ? <Text style={s.optionDesc}>{suffix}</Text> : null}
      </View>
    </View>
  );
}

export function StepHeader({ step, total, backHref, skipHref, onSkip, disabled }: { step: number; total: number; backHref: string; skipHref?: string; onSkip?: () => void; disabled?: boolean }) {
  const router = useRouter();
  return (
    <View style={s.header}>
      <Pressable onPress={() => (router.canGoBack() ? router.back() : router.replace(backHref as never))} accessibilityLabel="이전" style={s.iconButton}>
        <Text style={{ fontSize: 22, color: colors.ink }}>‹</Text>
      </Pressable>
      <View style={s.progress}>
        {Array.from({ length: total }, (_, i) => (
          <View key={i} style={[s.progressSeg, { backgroundColor: i < step ? colors.accent : colors.line }]} />
        ))}
      </View>
      {onSkip ? <Pressable onPress={onSkip} disabled={disabled} accessibilityRole="button"><Text style={s.skip}>건너뛰기</Text></Pressable> : skipHref ? <Link href={skipHref as never} style={s.skip}>건너뛰기</Link> : <View style={{ width: 56 }} />}
    </View>
  );
}

export function ScoreBar({ label, points, max = 16, auxiliary }: { label: string; points: number; max?: number; auxiliary?: boolean }) {
  return (
    <View style={s.scoreRow}>
      <Text style={[s.optionDesc, { color: colors.ink, width: 126 }]}>{label}</Text>
      <View style={s.track}><View style={[s.fill, { width: `${Math.min(100, (points / max) * 100)}%`, backgroundColor: auxiliary ? colors.terracotta : colors.accent }]} /></View>
      <Text style={[s.optionDesc, { color: colors.ink, fontFamily: fonts.semibold, width: 34, textAlign: "right" }]}>+{points}</Text>
    </View>
  );
}

export const Card = ({ children, style }: { children: React.ReactNode; style?: ViewStyle }) => <View style={[s.card, style]}>{children}</View>;

export function ErrorBox({ message, onRetry }: { message: string; onRetry?: () => void }) {
  return (
    <Card style={{ gap: 12 }}>
      <Body>{message}</Body>
      {onRetry ? <Button title="다시 시도" variant="outline" onPress={onRetry} /> : null}
    </Card>
  );
}

const s = StyleSheet.create({
  safe: { flex: 1, backgroundColor: colors.bg },
  scroll: { flexGrow: 1 },
  body: { flex: 1, width: "100%", maxWidth: 640, alignSelf: "center", paddingHorizontal: 24, paddingTop: 8, paddingBottom: 24, gap: 22 },
  title: { fontFamily: fonts.display, color: colors.ink, letterSpacing: -0.4 },
  label: { fontFamily: fonts.semibold, fontSize: 14, color: colors.ink },
  button: { height: 54, borderRadius: radius.button, alignItems: "center", justifyContent: "center" },
  buttonPrimary: { backgroundColor: colors.accent },
  buttonOutline: { borderWidth: 1.5, borderColor: colors.lineStrong },
  buttonText: { fontFamily: fonts.semibold, fontSize: 16 },
  chip: { height: 44, paddingHorizontal: 16, borderRadius: 22, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card, justifyContent: "center" },
  chipText: { fontFamily: fonts.body, fontSize: 14, color: colors.ink },
  selected: { borderColor: colors.accent, backgroundColor: colors.accentSoft },
  option: { minHeight: 52, paddingHorizontal: 16, paddingVertical: 12, borderRadius: radius.control, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card, flexDirection: "row", alignItems: "center", gap: 10 },
  optionTitle: { fontFamily: fonts.semibold, fontSize: 15, color: colors.ink, flexShrink: 0 },
  optionDesc: { fontFamily: fonts.body, fontSize: 13, color: colors.muted, flex: 1, textAlign: "right" },
  swatch: { width: 22, height: 22, borderRadius: 11 },
  field: { height: 52, borderRadius: radius.control, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card, paddingHorizontal: 16, flexDirection: "row", alignItems: "center", gap: 8 },
  fieldInput: { flex: 1, fontFamily: fonts.body, fontSize: 16, color: colors.ink },
  header: { height: 44, flexDirection: "row", alignItems: "center", gap: 12 },
  iconButton: { width: 44, height: 44, marginLeft: -10, alignItems: "center", justifyContent: "center" },
  progress: { flex: 1, flexDirection: "row", gap: 6 },
  progressSeg: { flex: 1, height: 4, borderRadius: 2 },
  skip: { fontFamily: fonts.body, fontSize: 14, color: colors.muted, width: 56, textAlign: "right" },
  scoreRow: { flexDirection: "row", alignItems: "center", gap: 10 },
  track: { flex: 1, height: 8, borderRadius: 4, backgroundColor: colors.divider },
  fill: { height: 8, borderRadius: 4 },
  card: { backgroundColor: colors.card, borderRadius: radius.card, borderWidth: 1, borderColor: colors.line, padding: 16 },
});
