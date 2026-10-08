import React, { useEffect, useRef, useState } from "react";
import { View } from "react-native";
import { Chip, Label, Muted } from "@/components/ui";
import { colors } from "@/theme";

type InstagramPost = { permalink: string; label: string; checked_at: string };
type InstagramWindow = Window & { instgrm?: { Embeds: { process: () => void } } };
let embedScript: Promise<void> | undefined;

function loadEmbeds() {
  if ((window as InstagramWindow).instgrm) return Promise.resolve();
  if (!embedScript) {
    embedScript = new Promise<void>((resolve, reject) => {
      const script = document.createElement("script");
      script.src = "https://www.instagram.com/embed.js";
      script.async = true;
      const timer = setTimeout(() => { script.remove(); reject(new Error("Instagram timeout")); }, 15000);
      script.onload = () => { clearTimeout(timer); resolve(); };
      script.onerror = () => { clearTimeout(timer); script.remove(); reject(new Error("Instagram unavailable")); };
      document.body.appendChild(script);
    }).catch(error => { embedScript = undefined; throw error; });
  }
  return embedScript;
}

function Embed({ post }: { post: InstagramPost }) {
  const host = useRef<HTMLDivElement>(null);
  const [failed, setFailed] = useState(false);
  const [narrow, setNarrow] = useState(false);
  useEffect(() => {
    const node = host.current;
    if (!node) return;
    let active = true;
    let rendered = false;
    const render = () => {
      const tooNarrow = node.clientWidth < 326;
      setNarrow(tooNarrow);
      if (tooNarrow || rendered) return;
      rendered = true;
      // React owns only the host; Instagram owns its blockquote/iframe subtree.
      const quote = document.createElement("blockquote");
      quote.className = "instagram-media";
      quote.dataset.instgrmPermalink = post.permalink;
      quote.dataset.instgrmVersion = "14";
      quote.style.cssText = "width:100%;max-width:540px;min-width:326px;margin:0 auto;background:white;";
      const link = document.createElement("a");
      link.href = post.permalink;
      link.textContent = "Instagram에서 원본 사진 보기";
      quote.appendChild(link);
      node.replaceChildren(quote);
      loadEmbeds().then(() => { if (active) (window as InstagramWindow).instgrm?.Embeds.process(); })
        .catch(() => { if (active) { node.replaceChildren(); setFailed(true); } });
    };
    render();
    const resize = new ResizeObserver(render);
    resize.observe(node);
    return () => { active = false; resize.disconnect(); node.replaceChildren(); };
  }, [post.permalink]);
  return <View style={{ gap: 12 }}>
    <div ref={host} data-testid="instagram-embed" style={{ width: "100%", overflow: "hidden", maxHeight: narrow ? 0 : undefined }} />
    {failed || narrow ? <Muted size={13}>이 화면에서 사진을 표시할 수 없어요. 아래에서 원본 게시물을 열어 주세요.</Muted> : null}
    <a href={post.permalink} target="_blank" rel="noopener noreferrer" style={{ color: colors.accentInk, fontSize: 14 }}>Instagram에서 원본 사진 보기 ↗</a>
  </View>;
}

export function InstagramPosts({ posts }: { posts: InstagramPost[] }) {
  const [selected, setSelected] = useState(0);
  const safePosts = posts.filter(p => /^https:\/\/www\.instagram\.com\/(p|reel)\/[A-Za-z0-9_-]{5,64}\/$/.test(p.permalink));
  const post = safePosts[selected] ?? safePosts[0];
  if (!post) return null;
  return <View testID="instagram-posts" style={{ gap: 12, marginHorizontal: -12 }}>
    <Label>인스타그램 장소 사진</Label>
    {safePosts.length > 1 ? <View style={{ flexDirection: "row", flexWrap: "wrap", gap: 8 }}>
      {safePosts.map((p, i) => <Chip key={p.permalink} label={`게시물 ${i + 1}`} selected={p === post} onPress={() => setSelected(i)} />)}
    </View> : null}
    <Muted size={13}>{post.label}</Muted>
    <Embed key={post.permalink} post={post} />
    <Muted size={11}>공개 원본 게시물 · 연결 확인 {post.checked_at}. 게시 당시의 모습으로 현재와 다를 수 있어요. 비공개 전환·삭제·Instagram 접속 제한 시 원본 보기가 제한될 수 있어요.</Muted>
  </View>;
}
