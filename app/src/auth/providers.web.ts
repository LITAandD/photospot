/** 웹 전용: 네이티브 SDK가 없으므로 개발용 로그인만. (웹 정식 지원 시 각 사의 웹 SDK로 교체) */
import { type TokenPair } from "@photospot/client";

import { api } from "@/api";

export type ProviderId = "google" | "apple" | "naver" | "kakao";
export class LoginCancelled extends Error {}
export const isExpoGo = false;

const notOnWeb = (name: string) => async (): Promise<TokenPair> => { throw new Error(`${name} 로그인은 앱(개발 빌드)에서만 쓸 수 있어요`); };
export const loginWithGoogle = notOnWeb("구글");
export const loginWithApple = notOnWeb("애플");
export const loginWithNaver = notOnWeb("네이버");
export const loginWithKakao = notOnWeb("카카오");
export const devLogin = (id: string) => api.auth.google(`dev:${id}`);
export const isAppleAvailable = (): Promise<boolean> => Promise.resolve(false);
export const deleteAccountWithProvider = () => api.deleteAccount();

export const PROVIDERS: { id: ProviderId; label: string; bg: string; fg: string; run: () => Promise<TokenPair> }[] = [];

export const linkWithProvider = async (_id: ProviderId) => { throw new Error("계정 연결은 설치형 Android·iOS 앱에서 이용해 주세요"); };
export const unlinkWithProvider = (id: ProviderId) => api.unlinkIdentity(id);
