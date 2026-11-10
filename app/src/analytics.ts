/**
 * 익명 퍼널 계측. 보내는 것은 이벤트 이름·경로(쿼리 제외)·무작위 세션 ID·UTM·작은 속성뿐이다.
 * 계정 ID·이메일·좌표·입력값 같은 개인정보는 넣지 않는다. 실패는 조용히 버리고 화면을 막지 않는다.
 * 서버: POST /preview/events (비로그인) · /v1/events (로그인) — api/analytics_routes.py 와 같은 payload.
 * 끄기: EXPO_PUBLIC_ANALYTICS=0. API 주소가 없는 개발 빌드에서는 보내지 않는다.
 */
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import { DEMO, tokenStore } from "@/api";

export type AnalyticsEvent = "landing_view" | "home_first_card" | "result_view" | "share_click" | "place_view" | "save"
  | "consent_accept" | "gps_allow" | "client_error";
export type AnalyticsProps = Record<string, string | number | boolean | null>;
export type AnalyticsPayload = { event: AnalyticsEvent; route: string; session_id: string; utm: Record<string, string>; props: AnalyticsProps };

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"] as const;
const SID_KEY = "photospot.analytics.sid", UTM_KEY = "photospot.analytics.utm";
const web = Platform.OS === "web";

const baseUrl = (): string | null => {
  if (process.env.EXPO_PUBLIC_ANALYTICS === "0") return null;
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (configured) return configured.replace(/\/+$/, "");
  if (DEMO && typeof window !== "undefined" && window.location?.origin) return window.location.origin;
  return null;
};
export const analyticsEnabled = () => baseUrl() !== null;

// --- 세션 ID: 기기(브라우저)에 남는 무작위 값. 계정과 연결하지 않는다 -------------------
const randomId = () => {
  try { return Crypto.randomUUID().replace(/-/g, ""); } catch { return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join(""); }
};
const VALID_SID = /^[A-Za-z0-9_-]{8,64}$/;
let sid: string | null = null;
let sidLoading: Promise<string> | null = null;
export function sessionId(): Promise<string> {
  if (sid) return Promise.resolve(sid);
  if (!sidLoading) sidLoading = (async () => {
    let stored: string | null = null;
    try { stored = web ? localStorage.getItem(SID_KEY) : await SecureStore.getItemAsync(SID_KEY); } catch { stored = null; }
    const value = stored && VALID_SID.test(stored) ? stored : randomId();
    if (value !== stored) {
      try { if (web) localStorage.setItem(SID_KEY, value); else await SecureStore.setItemAsync(SID_KEY, value); } catch { /* 이번 실행에서만 유지 */ }
    }
    sid = value;
    return value;
  })();
  return sidLoading;
}

// --- UTM: 첫 진입 주소의 utm_* 만, 탭(세션) 동안 유지 ----------------------------------
let utm: Record<string, string> = {};
/** 진입 주소(웹 location.href, 앱 Linking URL)에서 utm_* 를 읽어 둔다. 없으면 이전 값 유지 */
export function captureUtm(url: string | null | undefined): Record<string, string> {
  const query = url?.split("#")[0].split("?")[1];
  if (query) {
    const params = new URLSearchParams(query);
    const found: Record<string, string> = {};
    for (const key of UTM_KEYS) { const v = params.get(key); if (v) found[key] = v.slice(0, 100); }
    if (Object.keys(found).length) {
      utm = found;
      try { if (web) sessionStorage.setItem(UTM_KEY, JSON.stringify(found)); } catch { /* 메모리만 */ }
      return utm;
    }
  }
  if (!Object.keys(utm).length && web) {
    try { const saved = JSON.parse(sessionStorage.getItem(UTM_KEY) ?? "{}") as Record<string, string>; if (saved && typeof saved === "object") utm = saved; } catch { /* 무시 */ }
  }
  return utm;
}

// --- 현재 경로: _layout의 경로 변경 구독이 갱신한다 (쿼리 제외) ---------------------------
let currentRoute = "/";
export const setAnalyticsRoute = (pathname: string) => { currentRoute = cleanRoute(pathname); };
export const cleanRoute = (pathname: string) => {
  const path = (pathname || "/").split("?")[0].split("#")[0];
  return (path.startsWith("/") ? path : `/${path}`).slice(0, 120).replace(/\s/g, "");
};

const cleanProps = (props: AnalyticsProps = {}): AnalyticsProps => {
  const out: AnalyticsProps = {};
  for (const [key, value] of Object.entries(props).slice(0, 20)) {
    if (!/^[A-Za-z_][A-Za-z0-9_]{0,39}$/.test(key) || value === undefined) continue;
    out[key] = typeof value === "string" ? value.slice(0, 200) : value;
  }
  return out;
};

let sender: ((payload: AnalyticsPayload, url: string, token: string | null) => Promise<unknown>) | null = null;
/** 테스트·대체 전송 수단 주입 (기본은 fetch keepalive) */
export const setAnalyticsSender = (fn: typeof sender) => { sender = fn; };
const send = (payload: AnalyticsPayload, url: string, token: string | null) => {
  if (sender) return sender(payload, url, token);
  const headers: Record<string, string> = { "Content-Type": "application/json" };
  if (token) headers.Authorization = `Bearer ${token}`;
  return fetch(url, { method: "POST", headers, body: JSON.stringify(payload), keepalive: true });
};

/** 이벤트 한 건. 돌아오는 Promise는 기다리지 않아도 되며 절대 throw 하지 않는다 */
export async function track(event: AnalyticsEvent, props: AnalyticsProps = {}, route = currentRoute): Promise<boolean> {
  const base = baseUrl();
  if (!base) return false;
  try {
    const [session_id, tokens] = await Promise.all([sessionId(), Promise.resolve(tokenStore.get()).catch(() => null)]);
    const payload: AnalyticsPayload = { event, route: cleanRoute(route), session_id, utm: { ...utm }, props: cleanProps(props) };
    // 배포 형태로 경로를 고른다: DEMO 웹은 미리보기 API, 계정 API 빌드는 로그인 전에도 /v1/events (익명 허용)
    const path = DEMO ? "/preview/events" : "/v1/events";
    await send(payload, `${base}${path}`, tokens && !DEMO ? tokens.access : null);
    return true;
  } catch { return false; }
}

/** 화면 오류 보고(ErrorBoundary). 메시지는 200자까지, 스택·입력값은 보내지 않는다 */
export function reportClientError(error: unknown, route = currentRoute): Promise<boolean> {
  const e = error instanceof Error ? error : new Error(String(error));
  return track("client_error", { name: e.name.slice(0, 60), message: e.message.slice(0, 200), platform: Platform.OS }, route);
}
