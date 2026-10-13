import type { PlaceDetail } from "@photospot/client";
import React, { useEffect, useRef, useState } from "react";
import { Pressable, ScrollView, View } from "react-native";
import { Body, Button, ErrorBox, Label, Muted } from "@/components/ui";
import { api } from '@/api';
import { errorMessage } from '@/hooks';
import { PlacePhoto, PhotoCredit } from "@/components/place-photo";
import { colors } from "@/theme";

export function PlaceGallery({ photos, placeId, onLiked }: {
  photos: PlaceDetail["photos"]; placeId: string; onLiked: () => void;
}) {
  const [selectedUrl, setSelectedUrl] = useState(photos[0]?.url);
  const index = Math.max(0, photos.findIndex(p => p.url === selectedUrl));
  const [shown, setShown] = useState(12);
  const [change, setChange] = useState<{ photo_id: string; like_count: number; liked: boolean } | null>(null);
  const [saving, setSaving] = useState(false);
  const busy = useRef(false);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => { setChange(null); setShown(v => Math.max(v, index + 1)); }, [photos, index]);
  const original = photos[index];
  const selected = original && change?.photo_id === original.photo_id ? { ...original, ...change } : original;
  const toggle = async () => {
    if (busy.current || !selected?.photo_id || !selected.likes_enabled) return;
    busy.current = true; setSaving(true); setError(null);
    try {
      const result = await api.setPhotoLike(placeId, selected.photo_id, !selected.liked);
      setChange(result); onLiked();
    } catch (e) { setError(errorMessage(e)); }
    finally { busy.current = false; setSaving(false); }
  };
  const select = (i: number) => { setSelectedUrl(photos[i].url); setShown(v => Math.max(v, i + 1)); setError(null); };
  if (!selected) return null;
  return <View testID="place-gallery" style={{ gap: 12 }}>
    <Label>장소 사진 · {photos.length}장</Label>
    <PlacePhoto photo={selected} label={selected.title ?? "장소 사진"} style={{ width: "100%", height: 240, borderRadius: 12 }} />
    <PhotoCredit photo={selected} />
    {selected.photo_id ? <View style={{ gap: 8 }}>
      <View style={{ flexDirection: 'row', alignItems: 'center', gap: 12 }}>
        <Pressable testID="photo-like" accessibilityRole="button" aria-pressed={!!selected.liked}
          accessibilityLabel={`이 사진 좋아요 ${selected.like_count ?? 0}개`}
          accessibilityState={{ selected: !!selected.liked, disabled: saving || !selected.likes_enabled }}
          disabled={saving || !selected.likes_enabled} onPress={toggle}
          style={{ minHeight: 44, paddingHorizontal: 16, paddingVertical: 12, borderRadius: 12,
            borderWidth: 1, borderColor: selected.liked ? colors.accent : colors.line }}>
          <Body>{saving ? '저장 중…' : `${selected.liked ? '♥' : '♡'} 좋아요 ${selected.like_count ?? 0}`}</Body>
        </Pressable>
        {index === 0 ? <Muted size={12}>대표사진 · 정합성 근거</Muted> : null}
      </View>
      {error ? <ErrorBox message={error} /> : null}
      <Muted size={11}>{selected.likes_enabled
        ? '좋아요가 많은 사진을 대표사진으로 사용해요. 동점이면 기존 공간 사진 우선순위를 유지해요.'
        : '좋아요 저장소 연결을 준비하고 있어요.'}</Muted>
    </View> : null}
    {photos.length > 1 ? <>
      <View style={{ flexDirection: "row", gap: 12, alignItems: "center" }}>
        <View style={{ flex: 1 }}><Button title="이전 사진" variant="outline" disabled={index === 0 || saving} onPress={() => select(index - 1)} /></View>
        <Body size={12}>{index + 1} / {photos.length}</Body>
        <View style={{ flex: 1 }}><Button title="다음 사진" variant="outline" disabled={index >= photos.length - 1 || saving} onPress={() => select(index + 1)} /></View>
      </View>
      <ScrollView horizontal showsHorizontalScrollIndicator contentContainerStyle={{ gap: 8 }}>
        {photos.slice(0, shown).map((photo, i) => <Pressable key={photo.url} accessibilityRole="button"
          accessibilityLabel={`사진 ${i + 1} 선택, 좋아요 ${photo.like_count ?? 0}개`} accessibilityState={{ selected: index === i, disabled: saving }} disabled={saving} onPress={() => select(i)}
          style={{ borderWidth: 2, borderColor: index === i ? colors.accent : colors.line, borderRadius: 10, overflow: "hidden" }}>
          <PlacePhoto photo={photo} label={`사진 ${i + 1}`} style={{ width: 76, height: 64 }} />
          {photo.likes_enabled ? <Muted size={11}>♥ {photo.like_count ?? 0}</Muted> : null}
        </Pressable>)}
      </ScrollView>
      {shown < photos.length ? <Button title="사진 더 보기" variant="outline" onPress={() => setShown(Math.min(photos.length, shown + 12))} /> : null}
    </> : null}
    <Muted size={11}>촬영 시기에 따라 현재 모습과 다를 수 있어요.</Muted>
  </View>;
}
