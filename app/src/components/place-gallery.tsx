import type { PlaceDetail } from "@photospot/client";
import React, { useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Body, Button, Label, Muted } from "@/components/ui";
import { PlacePhoto, PhotoCredit } from "@/components/place-photo";
import { colors } from "@/theme";

export function PlaceGallery({ photos }: { photos: PlaceDetail["photos"] }) {
  const [index, setIndex] = useState(0);
  const [shown, setShown] = useState(12);
  const selected = photos[Math.min(index, photos.length - 1)];
  if (!selected) return null;
  return <View testID="place-gallery" style={{ gap: 12 }}>
    <Label>장소 사진 · {photos.length}장</Label>
    <PlacePhoto photo={selected} label={selected.title ?? "장소 사진"} style={{ width: "100%", height: 240, borderRadius: 12 }} />
    <PhotoCredit photo={selected} />
    {photos.length > 1 ? <>
      <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
        <View style={{ flex: 1 }}><Button title="이전 사진" variant="outline" disabled={index === 0} onPress={() => setIndex(index - 1)} /></View>
        <Body size={12}>{index + 1} / {photos.length}</Body>
        <View style={{ flex: 1 }}><Button title="다음 사진" variant="outline" disabled={index >= photos.length - 1} onPress={() => { setIndex(index + 1); setShown(Math.max(shown, index + 2)); }} /></View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ gap: 8 }}>
        {photos.slice(0, shown).map((photo, i) => <Pressable key={photo.url} accessibilityRole="button"
          accessibilityLabel={`사진 ${i + 1} 선택`} accessibilityState={{ selected: index === i }} onPress={() => setIndex(i)}
          style={{ borderWidth: 2, borderColor: index === i ? colors.accent : colors.line, borderRadius: 10, overflow: "hidden" }}>
          <PlacePhoto photo={photo} label={`사진 ${i + 1}`} style={{ width: 76, height: 64 }} />
        </Pressable>)}
      </ScrollView>
      {shown < photos.length ? <Button title="사진 더 보기" variant="outline" onPress={() => setShown(Math.min(photos.length, shown + 12))} /> : null}
    </> : null}
    <Muted size={11}>촬영 시기에 따라 현재 모습과 다를 수 있어요.</Muted>
  </View>;
}
