import React, { useState } from "react";
import { Pressable, Text, View } from "react-native";
import { colors, fonts } from "@/theme";

export function ScoreDisclosure({ title, summary, children, testID }: {
  title: string; summary?: string; children: React.ReactNode; testID?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  return <View testID={testID} style={{ gap: expanded ? 12 : 0 }}>
    <Pressable accessibilityRole="button" accessibilityLabel={`${title} 상세`}
      accessibilityState={{ expanded }} aria-expanded={expanded} onPress={() => setExpanded(!expanded)}
      style={({ pressed }) => ({ minHeight: 48, flexDirection: "row", alignItems: "center", gap: 12, opacity: pressed ? 0.65 : 1 })}>
      <Text style={{ flex: 1, color: colors.ink, fontFamily: fonts.medium, fontSize: 13, lineHeight: 20 }}>{title}</Text>
      {summary ? <Text style={{ color: colors.accentInk, fontFamily: fonts.semibold, fontSize: 13 }}>{summary}</Text> : null}
      <Text style={{ color: colors.muted, fontSize: 17 }} aria-hidden>{expanded ? "⌃" : "⌄"}</Text>
    </Pressable>
    {expanded ? <View style={{ gap: 9, paddingBottom: 12 }}>{children}</View> : null}
  </View>;
}
