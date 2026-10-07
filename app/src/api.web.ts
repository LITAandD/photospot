/** 웹 전용: SecureStore 대신 localStorage (브라우저 개발·데모용) */
import { PhotoSpotClient, type TokenStore } from "@photospot/client";

import { demoFetch } from "./demo/fetch";

export const DEMO = process.env.EXPO_PUBLIC_DEMO === "1";
export const DEV_LOGIN = DEMO || (__DEV__ && process.env.EXPO_PUBLIC_DEV_LOGIN === "1");

const KEY = DEMO ? "photospot.demo.tokens" : "photospot.tokens";
export const tokenStore: TokenStore = {
  get() { try { const v = localStorage.getItem(KEY); return v ? JSON.parse(v) : null; } catch { return null; } },
  set(t) { localStorage.setItem(KEY, JSON.stringify(t)); },
  clear() { localStorage.removeItem(KEY); },
};

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
