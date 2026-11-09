/**
 * 공유 도우미. 빈 줄은 빼고, 돌아올 수 있는 공개 주소(utm_source=share)를 붙인다.
 * Web Share가 없거나 실패하면 클립보드에 복사하고, 그것도 안 되면 failed 를 돌려줘 화면이 안내한다.
 * 절대 throw 하지 않는다 (웹의 'Share is not supported' unhandled rejection 방지).
 */
import { Platform, Share } from "react-native";

/** 공개 웹 주소 (배포 도메인이 바뀌면 EXPO_PUBLIC_WEB_URL 한 곳만) */
export const PUBLIC_WEB_URL = (process.env.EXPO_PUBLIC_WEB_URL || "https://photospot.litaandd.com").replace(/\/+$/, "");

/** 공유용 주소: 공개 도메인 + 경로 + utm_source */
export function shareUrl(path = "/", source = "share", extra: Record<string, string | undefined> = {}): string {
  const url = new URL(path.startsWith("/") ? path : `/${path}`, `${PUBLIC_WEB_URL}/`);
  for (const [key, value] of Object.entries(extra)) if (value) url.searchParams.set(key, value);
  url.searchParams.set("utm_source", source);
  return url.toString();
}

/** 값이 없는 줄(라벨만 남는 줄)은 빼고 이어 붙인다 */
export function buildShareMessage(lines: (string | null | undefined | false)[]): string {
  return lines.map((line) => (typeof line === "string" ? line.trim() : "")).filter(Boolean).join("\n");
}

/** 라벨: 값 형식 한 줄. 값이 비면 null (줄 자체를 뺀다) */
export const shareLine = (label: string, items: string | string[] | null | undefined): string | null => {
  const value = Array.isArray(items) ? items.filter(Boolean).join(", ") : items?.trim() ?? "";
  return value ? `${label}: ${value}` : null;
};

export type ShareOutcome = "shared" | "copied" | "dismissed" | "failed";
export const SHARE_NOTICE: Record<ShareOutcome, string | null> = {
  shared: null, dismissed: null, copied: "링크와 내용을 복사했어요. 원하는 곳에 붙여 넣어 주세요.",
  failed: "이 기기에서는 공유 기능을 쓸 수 없어요. 화면을 캡처해 공유해 주세요.",
};

type Clipboard = { writeText(text: string): Promise<void> };
const clipboard = (): Clipboard | null => {
  try { const c = (globalThis as { navigator?: { clipboard?: Clipboard } }).navigator?.clipboard; return c && typeof c.writeText === "function" ? c : null; }
  catch { return null; }
};
const canShare = () => Platform.OS !== "web" || typeof (globalThis as { navigator?: { share?: unknown } }).navigator?.share === "function";

export async function copyText(text: string): Promise<boolean> {
  try { const c = clipboard(); if (!c) return false; await c.writeText(text); return true; } catch { return false; }
}

export async function shareText({ title, lines, url }: { title: string; lines: (string | null | undefined | false)[]; url?: string }): Promise<ShareOutcome> {
  const message = buildShareMessage(lines);
  const text = url ? buildShareMessage([message, url]) : message;
  if (!text) return "failed";
  if (canShare()) {
    try {
      // Android 공유 시트는 url 필드를 무시하므로 본문에 함께 넣는다. iOS·웹은 url 을 따로 전달해 링크 미리보기를 살린다
      const content = Platform.OS === "android" || !url ? { title, message: text } : { title, message, url };
      const result = await Share.share(content, { dialogTitle: title, subject: title });
      return result && result.action === Share.dismissedAction ? "dismissed" : "shared";
    } catch (e) {
      if (e instanceof Error && e.name === "AbortError") return "dismissed";  // 사용자가 공유 시트를 닫음
    }
  }
  return (await copyText(text)) ? "copied" : "failed";
}
