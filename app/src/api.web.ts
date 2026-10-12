/**
 * 웹 전용 토큰 저장소: localStorage + 메모리.
 * httpOnly 쿠키가 더 안전하지만 현재 API는 토큰을 JSON으로 주고 Authorization 헤더로만 받으며(쿠키 갱신 엔드포인트 없음),
 * 웹에는 운영 로그인 제공자가 없어(개발 로그인·체험 모드만) 새로고침 후에도 유지되는 저장소가 필요하다.
 * 저장소가 막힌 브라우저(사생활 보호 모드 등)에서는 메모리에만 두고, XSS 위험은 vercel.json의 CSP로 줄인다.
 */
import { PhotoSpotClient, type TokenStore } from "@photospot/client";

export const DEMO = process.env.EXPO_PUBLIC_DEMO === "1";
export const DEV_LOGIN = DEMO || (__DEV__ && process.env.EXPO_PUBLIC_DEV_LOGIN === "1");

const KEY = DEMO ? "photospot.demo.tokens" : "photospot.tokens";
type Tokens = { access: string; refresh: string };
let memory: Tokens | null = null;
const valid = (v: unknown): v is Tokens => !!v && typeof (v as Tokens).access === "string" && typeof (v as Tokens).refresh === "string";
export const tokenStore: TokenStore = {
  get() {
    let raw: string | null;
    try { raw = localStorage.getItem(KEY); } catch { return memory; }       // 저장소 차단: 메모리만
    try { const parsed: unknown = raw ? JSON.parse(raw) : null; return valid(parsed) ? parsed : null; } catch { return null; }
  },
  set(t) { memory = t; try { localStorage.setItem(KEY, JSON.stringify(t)); } catch { /* 메모리에만 유지 */ } },
  clear() { memory = null; try { localStorage.removeItem(KEY); } catch { /* 이미 접근 불가 */ } },
};

/** 체험 모드 코드·데이터는 DEMO일 때만 불러온다 (운영 번들에서는 분리된 청크로 남고 실행되지 않음) */
const demoFetch: typeof fetch = (input, init) => import("./demo/fetch").then((m) => m.demoFetch(input, init));

const signedOutListeners = new Set<() => void>();
export const onSignedOut = (fn: () => void) => { signedOutListeners.add(fn); return () => { signedOutListeners.delete(fn); }; };

export const api = new PhotoSpotClient({
  baseUrl: DEMO && typeof window !== "undefined" ? window.location.origin
    : process.env.EXPO_PUBLIC_API_BASE_URL ?? "http://localhost:8000",
  tokens: tokenStore,
  onSignedOut: () => signedOutListeners.forEach((fn) => fn()),
  fetch: DEMO ? demoFetch : undefined,
});

export const today = () => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
