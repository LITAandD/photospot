import type { SajuIn } from "@photospot/client";
import React from "react";
import { View } from "react-native";
import { BIRTH_HOURS } from "@/birth-input";
import { Label } from "@/components/ui";
import { colors, fonts } from "@/theme";

export function BirthHourSelect({ value, onChange, disabled }: {
  value: SajuIn["birth_hour_branch"]; onChange: (value: SajuIn["birth_hour_branch"]) => void; disabled?: boolean;
}) {
  return <View style={{ gap: 8 }}>
    <Label>태어난 시</Label>
    <select aria-label="태어난 시" value={value ?? ""} disabled={disabled}
      onChange={(event) => onChange((event.target.value || null) as SajuIn["birth_hour_branch"])}
      style={{ width: "100%", minHeight: 52, borderRadius: 12, border: `1.5px solid ${colors.line}`,
        backgroundColor: colors.card, color: colors.ink, fontFamily: fonts.body, fontSize: 16, padding: "0 12px" }}>
      <option value="">모름</option>
      {BIRTH_HOURS.map((hour) => <option key={hour.id} value={hour.id}>{hour.label} ({hour.range})</option>)}
    </select>
  </View>;
}
