import type { SajuIn } from "@photospot/client";
import React, { useState } from "react";
import { Pressable, ScrollView, Text, View } from "react-native";
import { BIRTH_HOURS } from "@/birth-input";
import { Label } from "@/components/ui";
import { colors, fonts } from "@/theme";

export function BirthHourSelect({ value, onChange, disabled }: {
  value: SajuIn["birth_hour_branch"]; onChange: (value: SajuIn["birth_hour_branch"]) => void; disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const options = [{ id: null, label: "모름" }, ...BIRTH_HOURS.map((h) => ({ id: h.id, label: `${h.label} (${h.range})` }))];
  const selected = options.find((option) => option.id === value) ?? options[0];
  return <View style={{ gap: 8 }}>
    <Label>태어난 시</Label>
    <Pressable accessibilityRole="button" accessibilityLabel={`태어난 시: ${selected.label}`}
      accessibilityState={{ expanded: open, disabled }} disabled={disabled} onPress={() => setOpen(!open)}
      style={{ minHeight: 52, padding: 14, borderRadius: 12, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card }}>
      <Text style={{ fontFamily: fonts.body, fontSize: 16, color: colors.ink }}>{selected.label}　{open ? "▴" : "▾"}</Text>
    </Pressable>
    {open && !disabled ? <ScrollView nestedScrollEnabled keyboardShouldPersistTaps="handled"
      accessibilityRole="menu" accessibilityLabel="태어난 시 선택" style={{ maxHeight: 240, borderRadius: 12, borderWidth: 1, borderColor: colors.line }}>
      {options.map((option) => <Pressable key={option.id ?? "unknown"} accessibilityRole="menuitem"
        accessibilityState={{ selected: value === option.id }} onPress={() => { onChange(option.id); setOpen(false); }}
        style={{ minHeight: 48, padding: 14, backgroundColor: value === option.id ? colors.accentSoft : colors.card }}>
        <Text style={{ fontFamily: fonts.body, fontSize: 15, color: colors.ink }}>{option.label}{value === option.id ? " ✓" : ""}</Text>
      </Pressable>)}
    </ScrollView> : null}
  </View>;
}
