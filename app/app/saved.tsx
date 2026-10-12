import type { Bookmark } from "@photospot/client";
import React from "react";
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
      ListFooterComponent={<Button title="추천 장소로 돌아가기" variant="outline" onPress={() => router.replace("/home")} />} />
  </Screen>;
}
