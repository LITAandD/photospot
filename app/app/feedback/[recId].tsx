import { submitVisit, type UploadFile } from "@photospot/client";
import * as ImagePicker from "expo-image-picker";
import { useLocalSearchParams, useRouter } from "expo-router";
import React, { useState } from "react";
import { Platform, Pressable, StyleSheet, Text, View } from "react-native";

import { api } from "@/api";
import { Body, Button, Chip, ErrorBox, Label, Muted, Screen, Title } from "@/components/ui";
import { errorMessage } from "@/hooks";
import { colors, fonts } from "@/theme";

const CHIPS: [string, string, string][] = [
  ["lighting", "warm_artificial", "조명이 더 노랬어요"],
  ["crowd_level", "busy", "생각보다 붐볐어요"],
  ["scale", "compact", "공간이 좁았어요"],
  ["color_temp", "warm", "배경색이 달랐어요"],
];

export default function Feedback() {
  const { recId, name, spot } = useLocalSearchParams<{ recId: string; name?: string; spot?: string }>();
  const router = useRouter();
  const [rating, setRating] = useState<number | null>(null);
  const [picked, setPicked] = useState<Record<string, string>>({});
  const [photo, setPhoto] = useState<{ uri: string; name: string; type: string } | null>(null);
  const [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const choose = async () => {
    try {
    const r = await ImagePicker.launchImageLibraryAsync({ mediaTypes: ["images"], quality: 0.9 });
    if (!r.canceled) {
      if ((r.assets[0].fileSize ?? 0) > 15 * 1024 * 1024) throw new Error("사진은 15MB까지 올릴 수 있어요");
      setPhoto({ uri: r.assets[0].uri, name: r.assets[0].fileName ?? "photo.jpg", type: r.assets[0].mimeType ?? "image/jpeg" });
    }
    } catch (e) { setError(errorMessage(e)); }
  };
  const send = async () => {
    if (busy) return;
    if (!/^\d+$/.test(recId) || Number(recId) <= 0) return setError("추천 목록에서 장소를 다시 열어 주세요");
    if (photo && (!consent || !spot)) return setError("사진 분석에 동의하거나 선택한 사진을 지워주세요");
    setBusy(true);
    setError(null);
    try {
      if (photo && consent) await api.grantConsent("photo_analysis");
      const file: UploadFile | undefined = photo ? (Platform.OS === "web" ? await (await fetch(photo.uri)).blob() : photo) : undefined;
      const { photoStatus } = await submitVisit(api, {
        recommendationId: Number(recId), rating: rating ?? undefined, visited: true,
        corrections: picked, photo: file && consent && spot ? { spotId: spot, file } : undefined,
      });
      if (photoStatus === "consent_required") { setError("후기는 저장했지만 사진은 업로드되지 않았어요. 분석 동의를 확인해 주세요"); return; }
      router.dismissAll();
      router.replace("/home");
    } catch (e) {
      setError(errorMessage(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <Screen>
      <Pressable onPress={() => router.back()} accessibilityLabel="닫기" style={s.close}><Text style={{ fontSize: 20 }}>×</Text></Pressable>
      <Title size={26}>{name ?? "이 장소"},{"\n"}사진은 잘 나왔나요?</Title>
      <View style={{ gap: 10 }}>
        <Label>추천이 얼마나 잘 맞았나요?</Label>
        <View style={{ flexDirection: "row", gap: 8 }}>
          {[1, 2, 3, 4, 5].map((n) => (
            <Pressable key={n} onPress={() => setRating(n)} accessibilityLabel={`${n}점`} accessibilityState={{ selected: rating === n }}
              style={[s.rate, rating === n && { borderColor: colors.accent, backgroundColor: colors.accentSoft }]}>
              <Text style={[s.rateText, rating === n && { color: colors.accentInk }]}>{n}</Text>
            </Pressable>
          ))}
        </View>
        <View style={{ flexDirection: "row", justifyContent: "space-between" }}><Muted size={12}>전혀 안 맞음</Muted><Muted size={12}>딱 맞음</Muted></View>
      </View>
      <View style={{ gap: 10 }}>
        <Label>찍은 사진 올리기 <Muted>(선택)</Muted></Label>
        <Pressable onPress={choose} accessibilityRole="button" style={s.upload}><Body size={14}>{photo ? "사진 1장 선택됨 · 바꾸기" : "사진 선택"}</Body></Pressable>
        {photo ? <Button title="선택한 사진 지우기" variant="outline" onPress={() => setPhoto(null)} /> : null}
        <Pressable onPress={() => setConsent(!consent)} accessibilityRole="checkbox" accessibilityState={{ checked: consent }}
          style={{ flexDirection: "row", gap: 10, alignItems: "flex-start" }}>
          <View style={[s.checkbox, consent && { backgroundColor: colors.accent, borderColor: colors.accent }]} />
          <View style={{ flex: 1 }}><Muted size={13}>장면 분석에 사진을 사용하는 데 동의해요. 위치·기기 메타데이터는 제거하고, 사진은 다른 사용자에게 공개하지 않아요. 얼굴·개인정보가 없는 배경 사진을 올려주세요.</Muted></View>
        </Pressable>
      </View>
      <View style={{ gap: 10 }}>
        <Label>실제와 달랐던 점이 있나요?</Label>
        <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
          {CHIPS.map(([attr, value, label]) => (
            <Chip key={attr} label={label} selected={picked[attr] === value}
              onPress={() => setPicked((cur) => { const next = { ...cur }; if (next[attr]) delete next[attr]; else next[attr] = value; return next; })} />
          ))}
        </View>
      </View>
      <View style={{ flex: 1 }} />
      {error ? <ErrorBox message={error} /> : null}
      <Button title="보내기" onPress={send} loading={busy} />
    </Screen>
  );
}

const s = StyleSheet.create({
  close: { width: 44, height: 44, marginLeft: -10, alignItems: "center", justifyContent: "center" },
  rate: { flex: 1, height: 48, borderRadius: 12, borderWidth: 1.5, borderColor: colors.line, backgroundColor: colors.card, alignItems: "center", justifyContent: "center" },
  rateText: { fontFamily: fonts.semibold, fontSize: 16, color: colors.ink },
  upload: { height: 96, borderRadius: 14, borderWidth: 1.5, borderStyle: "dashed", borderColor: colors.lineStrong, backgroundColor: colors.card, alignItems: "center", justifyContent: "center" },
  checkbox: { width: 20, height: 20, borderRadius: 5, borderWidth: 1.5, borderColor: colors.lineStrong, marginTop: 1 },
});
