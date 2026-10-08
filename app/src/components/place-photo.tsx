import React, { useState } from "react";
import { Image, Linking, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";
import { colors, fonts } from "@/theme";
import { photoAllowsModifications } from "@photospot/client";

type Photo = { url: string; attribution: string; keep_aspect_ratio: boolean; license?: string; source_url?: string | null; license_url?: string | null; original_url?: string | null };

export function PhotoCredit({ photo }: { photo: Photo }) {
  const [error, setError] = useState(false);
  const open = (url: string) => { setError(false); Linking.openURL(url).catch(() => setError(true)); };
  return <View testID="photo-credit" style={{ gap: 3 }}>
    <Text style={styles.creditText}>{photo.attribution} {photo.license ? `· ${photo.license}` : ""}</Text>
    {/creativecommons\.org\/licenses\/by-sa\//i.test(photo.license_url ?? "") ? <Text style={styles.creditText}>크롭·스케치가 적용된 사진 표시에도 같은 CC BY-SA 이용 조건이 적용됩니다.</Text> : null}
    <View style={{ flexDirection: "row", gap: 14, flexWrap: "wrap" }}>
      {photo.source_url ? <Pressable accessibilityRole="link" onPress={() => open(photo.source_url!)}><Text style={styles.link}>사진 출처</Text></Pressable> : null}
      {photo.license_url ? <Pressable accessibilityRole="link" onPress={() => open(photo.license_url!)}><Text style={styles.link}>사진 이용 조건</Text></Pressable> : null}
      {photo.original_url ? <Pressable accessibilityRole="link" onPress={() => open(photo.original_url!)}><Text style={styles.link}>원본 사진</Text></Pressable> : null}
    </View>
    {error ? <Text style={styles.creditText}>링크를 열지 못했어요. 다시 시도해 주세요.</Text> : null}
  </View>;
}

export function PlacePhoto({ photo, style, label = "장소 사진", credit = false, fit, placeholder = "사진 준비 중" }: {
  photo?: Photo | null; style?: ViewStyle; label?: string; credit?: boolean; fit?: "contain" | "cover"; placeholder?: string;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  return <View style={[styles.frame, style, !photoAllowsModifications(photo) && { borderRadius: 0 }]}>
    {photo && failedUrl !== photo.url ? <Image testID="place-photo-image" source={{ uri: photo.url }} accessibilityLabel={label}
      style={StyleSheet.absoluteFill} resizeMode={!photoAllowsModifications(photo) ? "contain" : fit ?? (photo.keep_aspect_ratio ? "contain" : "cover")}
      onError={() => setFailedUrl(photo.url)} /> : <Text style={[styles.placeholder, { textAlign: "center" }]}>{photo ? "사진을 불러올 수 없어요" : placeholder}</Text>}
    {photo && credit && failedUrl !== photo.url && photoAllowsModifications(photo) ? <Text style={styles.credit}>{photo.attribution} {photo.license ? `· ${photo.license}` : ""}</Text> : null}
  </View>;
}

const styles = StyleSheet.create({
  frame: { backgroundColor: colors.accentSoft, overflow: "hidden", justifyContent: "center", alignItems: "center" },
  placeholder: { color: colors.muted, fontFamily: fonts.body, fontSize: 11 },
  credit: { position: "absolute", bottom: 0, left: 0, right: 0, backgroundColor: "rgba(255,255,255,0.9)", padding: 6, fontFamily: fonts.body, fontSize: 10, color: colors.ink },
  creditText: { fontFamily: fonts.body, fontSize: 10, lineHeight: 15, color: colors.muted },
  link: { fontFamily: fonts.body, fontSize: 11, color: colors.accentInk, textDecorationLine: "underline" },
});
