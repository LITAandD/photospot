/**
 * 각 서비스의 네이티브 로그인 화면을 띄우고, 서버에 넘길 토큰만 돌려준다.
 *
 * 구글·네이버·카카오 SDK는 네이티브 모듈이라 Expo Go에는 없다. 그래서
 *  - 앱 시작 시점이 아니라 버튼을 누를 때만 require 로 불러오고 (파일을 열기만 해도 터지는 것을 방지)
 *  - Expo Go에서는 SDK를 부르지 않고 안내만 한다 (개발 빌드: npx expo run:ios / run:android 필요)
 * Expo Go에서 흐름을 볼 땐 서버 DEV_LOGIN=1 과 devLogin() 을 쓴다.
 */
import { ApiError, type LoginIn, type TokenPair } from "@photospot/client";
import Constants, { ExecutionEnvironment } from "expo-constants";
import * as Crypto from "expo-crypto";
import { Platform } from "react-native";

import { api } from "@/api";

export type ProviderId = "google" | "apple" | "naver" | "kakao";

export class LoginCancelled extends Error {}
export class NeedsDevBuild extends Error {
  constructor(name: string) { super(`${name} 로그인은 Expo Go에서 쓸 수 없어요. 개발 빌드에서 확인해 주세요`); }
}

export const isExpoGo = Constants.executionEnvironment === ExecutionEnvironment.StoreClient;

async function credentialsGoogle(): Promise<LoginIn> {
  if (isExpoGo) throw new NeedsDevBuild("구글");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { GoogleSignin, isSuccessResponse, isErrorWithCode, statusCodes } = require("@react-native-google-signin/google-signin") as typeof import("@react-native-google-signin/google-signin");
  GoogleSignin.configure({
    webClientId: process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID,          // ID 토큰 발급에 필요 (서버 GOOGLE_CLIENT_IDS에도 포함)
    iosClientId: process.env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID,
  });
  try {
    await GoogleSignin.hasPlayServices();
    const res = await GoogleSignin.signIn();
    if (!isSuccessResponse(res) || !res.data.idToken) throw new LoginCancelled();
    return { token: res.data.idToken };
  } catch (e) {
    if (isErrorWithCode(e) && e.code === statusCodes.SIGN_IN_CANCELLED) throw new LoginCancelled();
    throw e;
  }
}

async function credentialsApple(): Promise<LoginIn> {
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const AppleAuthentication = require("expo-apple-authentication") as typeof import("expo-apple-authentication");
  const nonce = Crypto.randomUUID();
  const hashed = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, nonce);   // 애플엔 해시를, 서버엔 원문을
  try {
    const cred = await AppleAuthentication.signInAsync({
      requestedScopes: [AppleAuthentication.AppleAuthenticationScope.FULL_NAME, AppleAuthentication.AppleAuthenticationScope.EMAIL],
      nonce: hashed,
    });
    if (!cred.identityToken || !cred.authorizationCode) throw new LoginCancelled();
    const name = [cred.fullName?.familyName, cred.fullName?.givenName].filter(Boolean).join("") || undefined;   // 첫 로그인에만 옴
    return { token: cred.identityToken, nonce, name, authorization_code: cred.authorizationCode };
  } catch (e) {
    if ((e as { code?: string }).code === "ERR_REQUEST_CANCELED") throw new LoginCancelled();
    throw e;
  }
}

async function credentialsNaver(): Promise<LoginIn> {
  if (isExpoGo) throw new NeedsDevBuild("네이버");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const NaverLogin = (require("@react-native-seoul/naver-login") as typeof import("@react-native-seoul/naver-login")).default;
  NaverLogin.initialize({
    appName: "포토스팟",
    consumerKey: process.env.EXPO_PUBLIC_NAVER_CLIENT_ID ?? "",
    consumerSecret: process.env.EXPO_PUBLIC_NAVER_CLIENT_SECRET ?? "",
    serviceUrlSchemeIOS: "photospot",
  });
  const { isSuccess, successResponse } = await NaverLogin.login();
  if (!isSuccess || !successResponse) throw new LoginCancelled();
  return { token: successResponse.accessToken };
}

async function credentialsKakao(): Promise<LoginIn> {
  if (isExpoGo) throw new NeedsDevBuild("카카오");
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const { login } = require("@react-native-seoul/kakao-login") as typeof import("@react-native-seoul/kakao-login");
  const res = await login();                                           // 카카오톡 앱이 있으면 앱으로, 없으면 웹으로
  return { token: res.accessToken };
}

const credentials = { google: credentialsGoogle, apple: credentialsApple, naver: credentialsNaver, kakao: credentialsKakao };
async function loginProvider(id: ProviderId): Promise<TokenPair> {
  const value = await credentials[id]();
  if (id === "apple") return api.auth.apple(value.token, { nonce: value.nonce ?? undefined, name: value.name ?? undefined, authorizationCode: value.authorization_code ?? undefined });
  return api.auth[id](value.token);
}
export const loginWithGoogle = () => loginProvider("google");
export const loginWithApple = () => loginProvider("apple");
export const loginWithNaver = () => loginProvider("naver");
export const loginWithKakao = () => loginProvider("kakao");
export async function linkWithProvider(id: ProviderId) {
  const value = await credentials[id]();
  await api.linkIdentity(id, value.token, { nonce: value.nonce ?? undefined, name: value.name ?? undefined, authorizationCode: value.authorization_code ?? undefined });
}
export async function unlinkWithProvider(id: ProviderId) {
  try { await api.unlinkIdentity(id); }
  catch (error) {
    if (id !== "apple" || !(error instanceof ApiError) || error.status !== 409 || !error.message.includes("재인증")) throw error;
    const value = await credentialsApple();
    await api.unlinkIdentity(id, { apple: { identity_token: value.token, authorization_code: value.authorization_code!, nonce: value.nonce! } });
  }
}

/** Expo Go 개발용 (서버 DEV_LOGIN=1) */
export const devLogin = (id: string) => api.auth.google(`dev:${id}`);

export async function deleteAccountWithProvider() {
  try { await api.deleteAccount(); return; }
  catch (error) { if (!(error instanceof ApiError) || error.status !== 409) throw error; }
  if (Platform.OS !== "ios") throw new Error("기존 Apple 계정의 인증을 갱신해야 해요. iOS에서 Apple로 다시 로그인한 뒤 삭제할 수 있어요.");
  const AppleAuthentication = require("expo-apple-authentication") as typeof import("expo-apple-authentication");
  const nonce = Crypto.randomUUID();
  const hashed = await Crypto.digestStringAsync(Crypto.CryptoDigestAlgorithm.SHA256, nonce);
  try {
    const cred = await AppleAuthentication.signInAsync({ requestedScopes: [], nonce: hashed });
    if (!cred.identityToken || !cred.authorizationCode) throw new LoginCancelled();
    await api.deleteAccount({ apple: { identity_token: cred.identityToken, authorization_code: cred.authorizationCode, nonce } });
  } catch (error) {
    if ((error as { code?: string }).code === "ERR_REQUEST_CANCELED") throw new LoginCancelled();
    throw error;
  }
}

export const isAppleAvailable = async (): Promise<boolean> => {
  if (Platform.OS !== "ios") return false;
  // eslint-disable-next-line @typescript-eslint/no-require-imports
  const AppleAuthentication = require("expo-apple-authentication") as typeof import("expo-apple-authentication");
  return AppleAuthentication.isAvailableAsync();
};

const configured: Record<ProviderId, boolean> = {
  google: !!process.env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID,
  apple: Platform.OS === "ios",
  kakao: !!process.env.EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY,
  naver: !!process.env.EXPO_PUBLIC_NAVER_CLIENT_ID && !!process.env.EXPO_PUBLIC_NAVER_CLIENT_SECRET,
};
export const PROVIDERS = ([
  { id: "kakao", label: "카카오로 시작하기", bg: "#FEE500", fg: "#191600", run: loginWithKakao },
  { id: "naver", label: "네이버로 시작하기", bg: "#03C75A", fg: "#FFFFFF", run: loginWithNaver },
  { id: "google", label: "Google로 시작하기", bg: "#FFFFFF", fg: "#1F1D1A", run: loginWithGoogle },
  { id: "apple", label: "Apple로 시작하기", bg: "#000000", fg: "#FFFFFF", run: loginWithApple },
] as { id: ProviderId; label: string; bg: string; fg: string; run: () => Promise<TokenPair> }[]).filter((p) => configured[p.id] && (!isExpoGo || p.id === "apple"));
