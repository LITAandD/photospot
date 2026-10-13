import React, { useState } from "react";
import { Linking, View } from "react-native";
import { Button, Label, Muted } from "@/components/ui";
import { isInstagramPermalink, safeInstagramPosts, type InstagramPost } from "./instagram-link";

export type { InstagramPost };

export function InstagramPosts({ posts: all }: { posts: InstagramPost[] }) {
  const [error, setError] = useState(false);
  const posts = safeInstagramPosts(all);
  if (!posts.length) return null;
  return <View testID="place-photo-source-links" style={{ gap: 12 }}>
    <Label>장소 사진 원본 링크</Label>
    <Muted size={13}>앱에서 보여드릴 재사용 허용 공간 사진을 확인 중이에요. 원본 게시물에서 장소를 살펴볼 수 있어요.</Muted>
    {posts.map(post => <Button key={post.permalink} title={post.label} variant="outline"
      onPress={() => { setError(false); if (!isInstagramPermalink(post.permalink)) return setError(true); Linking.openURL(post.permalink).catch(() => setError(true)); }} />)}
    {error ? <Muted>게시물을 열지 못했어요. 다시 시도해 주세요.</Muted> : null}
    <Muted size={12}>Instagram에서 열려요. 게시 당시의 모습으로 현재와 다를 수 있어요.</Muted>
  </View>;
}
