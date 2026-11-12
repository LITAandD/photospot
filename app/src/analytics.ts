/**
 * 선택 동의 기반 이용 이벤트 (순차 퍼널이 아님). 보내는 것은 이벤트 이름·경로(쿼리 제외)·무작위 세션 ID·UTM·작은 속성뿐이다.
 * 계정 ID·이메일·좌표·입력값은 보내지 않는다. 전송 실패는 false로 반환하고 화면을 막지 않는다.
 * 서버: POST /preview/events (비로그인) · /v1/events (로그인) — api/analytics_routes.py 와 같은 payload.
 * 끄기: EXPO_PUBLIC_ANALYTICS=0. API 주소가 없는 개발 빌드에서는 보내지 않는다.
 */
import * as Crypto from "expo-crypto";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

import { DEMO, tokenStore } from "@/api";

export type AnalyticsEvent = "landing_view" | "home_first_card" | "result_view" | "share_click" | "place_view" | "save"
  | "consent_accept" | "gps_allow" | "client_error"
  | "recommendation_request" | "recommendation_result" | "card_impression" | "map_open" | "empty_result" | "recommendation_error";
export type AnalyticsProps = Record<string, string | number | boolean | null>;
export type AnalyticsPayload = { event: AnalyticsEvent; route: string; session_id: string; utm: Record<string, string>; props: AnalyticsProps };

const UTM_KEYS = ["utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"] as const;
const SID_KEY = "photospot.analytics.visit.v2", UTM_KEY = "photospot.analytics.utm";
const TEST_KEY = "photospot.analytics.test.v2";
const CHOICE_KEY = "photospot.analytics.choice.v2", IDLE_MS = 30 * 60 * 1000;
const web = Platform.OS === "web";

const baseUrl = (): string | null => {
  if (process.env.EXPO_PUBLIC_ANALYTICS === "0") return null;
  const configured = process.env.EXPO_PUBLIC_API_BASE_URL;
  if (configured) return configured.replace(/\/+$/, "");
  if (DEMO && typeof window !== "undefined" && window.location?.origin) return window.location.origin;
  return null;
};
export const analyticsEnabled = () => baseUrl() !== null;

// Explicit new opt-in; old policy acceptance never implies a new analytics choice.
let choice: boolean | null = null;
export async function analyticsAllowed(): Promise<boolean> {
  if (!web && choice !== null) return choice;
  try { return (web ? localStorage.getItem(CHOICE_KEY) : await SecureStore.getItemAsync(CHOICE_KEY)) === 'allow'; }
  catch { return choice ?? false; }
}
export async function setAnalyticsChoice(allowed: boolean): Promise<void> {
  choice = allowed;
  visit = null;
  try {
    if (web) {
      localStorage.setItem(CHOICE_KEY, allowed ? 'allow' : 'deny');
      localStorage.removeItem('photospot.analytics.sid'); // legacy persistent browser ID: never migrate/link
      sessionStorage.removeItem(SID_KEY);
      if (!allowed) { sessionStorage.removeItem(UTM_KEY); sessionStorage.removeItem(TEST_KEY); }
    } else {
      await SecureStore.setItemAsync(CHOICE_KEY, allowed ? 'allow' : 'deny');
      await SecureStore.deleteItemAsync('photospot.analytics.sid');
    }
  } catch { /* choice still applies in this execution */ }
}
const randomId = () => {
  try { return Crypto.randomUUID().replace(/-/g, ''); }
  catch { return Array.from({ length: 32 }, () => Math.floor(Math.random() * 16).toString(16)).join(''); }
};
export const newRequestId = randomId;
type Visit = { id: string; last: number };
let visit: Visit | null = null;
export async function sessionId(): Promise<string> {
  const now = Date.now();
  if (!visit && web) {
    try { visit = JSON.parse(sessionStorage.getItem(SID_KEY) ?? 'null'); } catch { visit = null; }
  }
  if (!visit || !/^[A-Za-z0-9_-]{8,64}$/.test(visit.id) || !Number.isFinite(visit.last)
      || now - visit.last >= IDLE_MS || now < visit.last) visit = { id: randomId(), last: now };
  visit.last = now;
  try { if (web) sessionStorage.setItem(SID_KEY, JSON.stringify(visit)); } catch { /* memory only */ }
  return visit.id;
}

// --- UTM: 첫 진입 주소의 utm_* 만, 탭(세션) 동안 유지 ----------------------------------
let utm: Record<string, string> = {};
let testVisit = false;
/** 진입 주소(웹 location.href, 앱 Linking URL)에서 utm_* 를 읽어 둔다. 없으면 이전 값 유지 */
export function captureUtm(url: string | null | undefined): Record<string, string> {
  const query = url?.split("#")[0].split("?")[1];
  if (query) {
    const params = new URLSearchParams(query);
    if (params.get('traffic') === 'test') testVisit = true;
    const found: Record<string, string> = {};
    for (const key of UTM_KEYS) { const v = params.get(key); if (v && /^[A-Za-z0-9_.-]{1,60}$/.test(v)) found[key] = v; }
    if (Object.keys(found).length) {
      utm = found;
      // Attribution stays in memory until the user opts in.
      return utm;
    }
  }
  if (!Object.keys(utm).length && web) {
    try { if (new URL(document.referrer).hostname === "www.litaandd.com" || new URL(document.referrer).hostname === "litaandd.com") utm = { utm_source: "wix", utm_medium: "referral" }; } catch { /* absent referrer */ }
    try { const saved = JSON.parse(sessionStorage.getItem(UTM_KEY) ?? "{}") as Record<string, string>; if (saved && typeof saved === "object" && Object.keys(saved).length) { const safe: Record<string, string> = {}; for (const key of UTM_KEYS) if (typeof saved[key] === "string" && /^[A-Za-z0-9_.-]{1,60}$/.test(saved[key])) safe[key] = saved[key]; if (Object.keys(safe).length) utm = safe; } } catch { /* 무시 */ }
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
  if (!base || !(await analyticsAllowed())) return false;
  try {
    const [session_id, tokens] = await Promise.all([sessionId(), Promise.resolve(tokenStore.get()).catch(() => null)]);
    const payload: AnalyticsPayload = { event, route: cleanRoute(route), session_id, utm: { ...utm }, props: cleanProps(props) };
    // 배포 형태로 경로를 고른다: DEMO 웹은 미리보기 API, 계정 API 빌드는 로그인 전에도 /v1/events (익명 허용)
    const path = DEMO ? "/preview/events" : "/v1/events";
    // Neither profile input nor raw error text is collected. Test traffic is explicit.
    payload.props.schema_version = 2;
    testVisit = testVisit || process.env.EXPO_PUBLIC_ANALYTICS_TEST === "1" || web && (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1'
      || window.location.hostname.endsWith('.vercel.app') || new URLSearchParams(window.location.search).get('traffic') === 'test');
    try { if (web && sessionStorage.getItem(TEST_KEY) === '1') testVisit = true; } catch { /* memory only */ }
    payload.props.traffic = testVisit ? 'test' : 'production';
    if (!(await analyticsAllowed())) return false; // user may revoke while async session/token work runs
    try { if (web) { sessionStorage.setItem(UTM_KEY, JSON.stringify(utm)); if (testVisit) sessionStorage.setItem(TEST_KEY, '1'); } } catch { /* memory only */ }
    const response = await send(payload, `${base}${path}`, tokens && !DEMO ? tokens.access : null) as { ok?: boolean };
    return response?.ok === true;
  } catch { return false; }
}

/** 화면 오류 보고(ErrorBoundary). 오류 종류만 전송하며 메시지·스택·입력값은 보내지 않는다 */
export function reportClientError(error: unknown, route = currentRoute): Promise<boolean> {
  const e = error instanceof Error ? error : new Error(String(error));
  return track("client_error", { name: e.name.slice(0, 60), platform: Platform.OS }, route);
}

/** One request correlation ID, with empty/failure tracked separately; no coordinates or profile. */
export async function measuredRecommendations<T extends { items: unknown[] } | null>(load: () => Promise<T>, surface: string): Promise<T> {
  const request_id = newRequestId();
  void track('recommendation_request', { request_id, surface });
  try {
    const result = await load();
    if (result) void track(result.items.length ? 'recommendation_result' : 'empty_result', { request_id, surface, count: result.items.length });
    return result && Object.assign(result, { analytics_request_id: request_id });
  } catch (error) {
    void track('recommendation_error', { request_id, surface });
    throw error;
  }
}
