import type { Bookmark } from "@photospot/client";
import React, { useState } from "react";
import { useRouter } from "expo-router";
import { ActivityIndicator, FlatList, Pressable, View } from "react-native";
import { api, today } from "@/api";
import { Body, Button, Card, ErrorBox, Muted, Screen, Title } from "@/components/ui";
import { PlacePhoto } from "@/components/place-photo";
import { errorMessage, useAsync, useRefocus } from "@/hooks";

export default function Saved() {
  const router = useRouter();
  const saved = useAsync(() => api.getBookmarks(), []);
  useRefocus(saved.reload);
  // '처음으로'는 저장한 장소를 남기므로(서버 계약) 공용 기기에서는 여기서 따로 비운다 (S-11). 확인 뒤 하나씩 지우고 목록을 다시 받는다
  const [clearing, setClearing] = useState<"idle" | "confirm" | "busy">("idle");
  const [clearError, setClearError] = useState<string | null>(null);
  const clearAll = async () => {
    if (clearing === "busy") return;
    setClearing("busy"); setClearError(null);
    try {
      for (const p of saved.data ?? []) await api.removeBookmark(p.place_id);
      setClearing("idle"); saved.reload();
    } catch (e) { setClearError(errorMessage(e)); setClearing("confirm"); saved.reload(); }
  };
  const item = ({ item: p }: { item: Bookmark }) => <Pressable accessibilityRole="button" onPress={() => router.push({ pathname: "/place/[id]", params: { id: p.place_id, date: today() } })}>
    <Card style={{ flexDirection: "row", gap: 14 }}>
      <PlacePhoto photo={p.cover_photo} style={{ width: 76, height: 76, borderRadius: 12 }} label={p.name} />
      <View style={{ flex: 1, gap: 6 }}><Body>{p.name}</Body><Muted size={13}>{p.address ?? "주소 정보 준비 중"}</Muted>{p.cover_photo ? <Muted size={10}>{p.cover_photo.attribution} · {p.cover_photo.license}</Muted> : null}</View>
    </Card>
  </Pressable>;
  return <Screen scroll={false} style={{ paddingTop: 24, paddingBottom: 0 }}>
    <FlatList data={saved.data ?? []} keyExtractor={(p) => p.place_id} renderItem={item} style={{ flex: 1 }}
      contentContainerStyle={{ gap: 16, paddingBottom: 24 }} keyboardShouldPersistTaps="handled" initialNumToRender={8} windowSize={7}
      ListHeaderComponent={<View style={{ gap: 16 }}>
        <Title>저장한 장소</Title>
        <Muted>다음 촬영을 위해 모아둔 나만의 장소예요.</Muted>
        {saved.loading && !saved.data ? <ActivityIndicator /> : null}
        {saved.error ? <ErrorBox message={errorMessage(saved.error)} onRetry={saved.reload} /> : null}
      </View>}
      ListEmptyComponent={saved.data?.length === 0 ? <Card><Body>아직 저장한 장소가 없어요. 장소 상세에서 저장을 눌러보세요.</Body></Card> : null}
      ListFooterComponent={<View style={{ gap: 12 }}>
        {saved.data?.length ? (clearing === "idle"
          ? <Button title="저장 목록 비우기" variant="outline" onPress={() => setClearing("confirm")} />
          : <Card testID="saved-clear-confirm" style={{ gap: 12 }}>
            <Body>저장한 장소 {saved.data.length}곳을 모두 지울까요? 되돌릴 수 없어요.</Body>
            {clearError ? <ErrorBox message={clearError} /> : null}
            <Button title="모두 지우기" onPress={() => { void clearAll(); }} loading={clearing === "busy"} />
            <Button title="취소" variant="outline" disabled={clearing === "busy"} onPress={() => { setClearing("idle"); setClearError(null); }} />
          </Card>) : null}
        <Button title="추천 장소로 돌아가기" variant="outline" onPress={() => router.replace("/home")} />
      </View>} />
  </Screen>;
}
