import React, { useState } from "react";
import { Image, Linking, Platform, Pressable, StyleSheet, Text, View, type ViewStyle } from "react-native";
import { colors, fonts } from "@/theme";
import { photoAllowsModifications } from "@photospot/client";

type Photo = { url: string; attribution: string; keep_aspect_ratio: boolean; license?: string; source_url?: string | null; license_url?: string | null; original_url?: string | null; width?: number | null };

/** 목록 카드(72px)·갤러리 썸네일(76px)이 DPR 3까지 선명한 위키미디어 썸네일 폭. 상세 대표 사진은 원래 크기(960px)를 쓴다. */
export const THUMB_WIDTH = 320;
/** 이 폭 이하의 칸은 썸네일을 요청한다. */
export const SMALL_FRAME_PX = 160;
const WIKIMEDIA = /^https:\/\/(upload|thumb)\.wikimedia\.org(\/[^?#]*)(\?[^#]*)?$/;
const THUMB_NAME = /^(\d+)px-(.+)$/;

/** 위키미디어 사진 URL의 width px 썸네일. 다른 호스트, 이미 더 작은 썸네일, 원본보다 큰 요청은 그대로 둔다 (api/catalog_media.thumb_url과 같은 규칙). */
export function thumbnailUrl(url: string, width: number, originalWidth?: number | null): string {
  const match = WIKIMEDIA.exec(url);
  if (!match || (originalWidth && width >= originalWidth)) return url;
  const [, host, path, query = ""] = match;
  const segments = path.split("/");
  const last = segments.length - 1;
  if (segments.includes("thumb")) {
    const name = THUMB_NAME.exec(segments[last]);
    if (!name || Number(name[1]) <= width) return url;
    segments[last] = `${width}px-${name[2]}`;
  } else {
    if (segments.length < 6 || segments[2] !== "commons" || !/\.(jpe?g|png|gif)$/i.test(segments[last])) return url;
    segments.splice(3, 0, "thumb");
    segments.push(`${width}px-${segments[segments.length - 1]}`);
  }
  return `https://${host}.wikimedia.org${segments.join("/")}${query}`;
}

/** 칸이 작으면(목록 카드·갤러리 썸네일) 썸네일 폭, 아니면 undefined(원래 URL). thumbWidth={0}은 항상 원래 URL. */
export function thumbWidthFor(style?: ViewStyle, explicit?: number): number | undefined {
  if (explicit !== undefined) return explicit || undefined;
  const width = style?.width;
  return typeof width === "number" && width <= SMALL_FRAME_PX ? THUMB_WIDTH : undefined;
}

export function PhotoCredit({ photo }: { photo: Photo }) {
  const [error, setError] = useState(false);
  const open = (url: string) => { setError(false); Linking.openURL(url).catch(() => setError(true)); };
  return <View testID="photo-credit" style={{ gap: 3 }}>
    <Text style={styles.creditText}>{photo.attribution} {photo.license ? `· ${photo.license}` : ""}</Text>
    {/creativecommons\.org\/licenses\/by-sa\//i.test(photo.license_url ?? "") ? <Text style={styles.creditText}>크롭·스케치가 적용된 사진 표시에도 같은 CC BY-SA 이용 조건이 적용됩니다.</Text> : null}
    <View style={{ flexDirection: "row", gap: 14, flexWrap: "wrap" }}>
      {photo.source_url ? <Pressable accessibilityRole="link" style={{ minHeight: 44, justifyContent: "center" }} onPress={() => open(photo.source_url!)}><Text style={styles.link}>사진 출처</Text></Pressable> : null}
      {photo.license_url ? <Pressable accessibilityRole="link" style={{ minHeight: 44, justifyContent: "center" }} onPress={() => open(photo.license_url!)}><Text style={styles.link}>사진 이용 조건</Text></Pressable> : null}
      {photo.original_url ? <Pressable accessibilityRole="link" style={{ minHeight: 44, justifyContent: "center" }} onPress={() => open(photo.original_url!)}><Text style={styles.link}>원본 사진</Text></Pressable> : null}
    </View>
    {error ? <Text style={styles.creditText}>링크를 열지 못했어요. 다시 시도해 주세요.</Text> : null}
  </View>;
}

export function PlacePhoto({ photo, style, label = "장소 사진", credit = false, fit, placeholder = "사진 준비 중", thumbWidth }: {
  photo?: Photo | null; style?: ViewStyle; label?: string; credit?: boolean; fit?: "contain" | "cover"; placeholder?: string;
  /** 요청할 썸네일 폭. 생략하면 칸 폭으로 정한다(SMALL_FRAME_PX 이하 → THUMB_WIDTH). */
  thumbWidth?: number;
}) {
  const [failedUrl, setFailedUrl] = useState<string | null>(null);
  const [fullSizeFor, setFullSizeFor] = useState<string | null>(null);    // 썸네일을 못 받은 사진은 원래 URL로 한 번 더
  const width = thumbWidthFor(style, thumbWidth);
  const uri = photo ? (width && fullSizeFor !== photo.url ? thumbnailUrl(photo.url, width, photo.width) : photo.url) : null;
  const resizeMode = photo && !photoAllowsModifications(photo) ? "contain" : fit ?? (photo?.keep_aspect_ratio ? "contain" : "cover");
  const onError = () => {
    if (!photo) return;
    if (uri !== photo.url) setFullSizeFor(photo.url); else setFailedUrl(photo.url);
  };
  return <View style={[styles.frame, style, !photoAllowsModifications(photo) && { borderRadius: 0 }]}>
    {photo && uri && failedUrl !== photo.url
      ? Platform.OS === "web"
        // 웹은 <img> 하나만: RN Web Image는 같은 URL을 미리 읽기·숨은 <img>·배경으로 겹쳐 요청한다. 화면 밖 카드는 lazy.
        ? <img data-testid="place-photo-image" src={uri} alt={label} loading="lazy" decoding="async" onError={onError}
            style={{ position: "absolute", top: 0, left: 0, width: "100%", height: "100%", objectFit: resizeMode }} />
        : <Image testID="place-photo-image" source={{ uri }} accessibilityLabel={label} style={StyleSheet.absoluteFill} resizeMode={resizeMode} onError={onError} />
      : <Text style={[styles.placeholder, { textAlign: "center" }]}>{photo ? "사진을 불러올 수 없어요" : placeholder}</Text>}
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
