import { PhotoSpotClient, type TokenStore } from "@photospot/client";
import * as SecureStore from "expo-secure-store";
import Constants from "expo-constants";
import { Platform } from "react-native";

const ACCESS = "photospot.access", REFRESH = "photospot.refresh";
export const DEMO = false;
export const DEV_LOGIN = __DEV__ && process.env.EXPO_PUBLIC_DEV_LOGIN === "1";

/** 액세스·갱신 토큰을 기기 안전 저장소에 보관 */
export const tokenStore: TokenStore = {
  async get() {
    const [access, refresh] = await Promise.all([SecureStore.getItemAsync(ACCESS), SecureStore.getItemAsync(REFRESH)]);
    return access && refresh ? { access, refresh } : null;
  },
  async set(t) {
    await Promise.all([SecureStore.setItemAsync(ACCESS, t.access), SecureStore.setItemAsync(REFRESH, t.refresh)]);
  },
  async clear() {
    await Promise.all([SecureStore.deleteItemAsync(ACCESS), SecureStore.deleteItemAsync(REFRESH)]);
  },
};

/** 갱신까지 실패했을 때 로그인 화면으로 보내기 위한 구독 */
const signedOutListeners = new Set<() => void>();
export const onSignedOut = (fn: () => void) => { signedOutListeners.add(fn); return () => { signedOutListeners.delete(fn); }; };

export const api = new PhotoSpotClient({
  baseUrl: process.env.EXPO_PUBLIC_API_BASE_URL ?? `http://${Constants.expoConfig?.hostUri?.split(":")[0] ?? (Platform.OS === "android" ? "10.0.2.2" : "localhost")}:8000`,
  tokens: tokenStore,
  onSignedOut: () => signedOutListeners.forEach((fn) => fn()),
});

export const today = () => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);   // KST
