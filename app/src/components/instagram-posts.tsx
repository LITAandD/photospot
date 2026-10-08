import React, { useState } from "react";
import { Linking, View } from "react-native";
import { Button, Label, Muted } from "@/components/ui";

export type InstagramPost = { permalink: string; label: string; checked_at: string };

export function InstagramPosts({ posts }: { posts: InstagramPost[] }) {
  const [error, setError] = useState(false);
  if (!posts.length) return null;
  return <View style={{ gap: 12 }}>
    <Label>인스타그램 장소 사진</Label>
    {posts.map(post => <Button key={post.permalink} title={post.label} variant="outline"
      onPress={() => { setError(false); Linking.openURL(post.permalink).catch(() => setError(true)); }} />)}
    {error ? <Muted>게시물을 열지 못했어요. 다시 시도해 주세요.</Muted> : null}
    <Muted size={12}>공개 원본 게시물로 연결돼요. 게시 당시의 모습으로 현재와 다를 수 있어요.</Muted>
  </View>;
}
