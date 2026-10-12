/** Authenticated web sessions end on reload; preview profiles remain browser-local. */
import { PhotoSpotClient } from "@photospot/client";
import { createWebTokenStore } from "./web-token-store";
import { observableTokens } from './state/auth-session';

export const DEMO = process.env.EXPO_PUBLIC_DEMO === "1";
export const DEV_LOGIN = DEMO || (__DEV__ && process.env.EXPO_PUBLIC_DEV_LOGIN === "1");

export const tokenStore = observableTokens(createWebTokenStore(DEMO));

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
