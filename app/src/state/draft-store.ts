/**
 * 온보딩 입력 초안을 재시작 뒤에도 이어 가도록 보관한다. 웹은 탭 단위 sessionStorage, 앱은 SecureStore
 * (설치된 유일한 영구 저장소; 값은 선택한 프로필 항목뿐이고 비밀값은 아니다). 비우기(reset)는 저장분도 지운다.
 */
import type { Profile } from "@photospot/client";
import * as SecureStore from "expo-secure-store";
import { Platform } from "react-native";

export type StoredDraft = { profile: Profile; original: Profile | null };
const KEY = "photospot.onboarding-draft";
const web = Platform.OS === "web";
const FIELDS: (keyof Profile)[] = ["gender", "birth_year", "height_cm", "pc_season", "pc_subtone", "body_type", "mbti"];

const isProfile = (value: unknown): value is Profile =>
  !!value && typeof value === "object" && typeof (value as Profile).gender === "string";
const parse = (text: string | null): StoredDraft | null => {
  if (!text) return null;
  try {
    const value = JSON.parse(text) as Partial<StoredDraft>;
    if (!isProfile(value.profile)) return null;
    return { profile: value.profile, original: isProfile(value.original) ? value.original : null };
  } catch { return null; }
};

export async function readDraft(): Promise<StoredDraft | null> {
  try { return parse(web ? sessionStorage.getItem(KEY) : await SecureStore.getItemAsync(KEY)); } catch { return null; }
}

export async function writeDraft(draft: StoredDraft | null): Promise<void> {
  try {
    if (!draft) { if (web) sessionStorage.removeItem(KEY); else await SecureStore.deleteItemAsync(KEY); return; }
    const text = JSON.stringify(draft);
    if (web) sessionStorage.setItem(KEY, text); else await SecureStore.setItemAsync(KEY, text);
  } catch { /* 저장소를 못 쓰면 이번 실행에서만 유지 */ }
}

/** base 와 비교해 사용자가 바꾼 항목만 (저장된 프로필 위에 다시 얹을 변경분) */
export function touchedFields(profile: Profile, base: Profile): Partial<Profile> {
  const patch: Partial<Profile> = {};
  for (const key of FIELDS) if ((profile[key] ?? null) !== (base[key] ?? null)) (patch as Record<string, unknown>)[key] = profile[key] ?? null;
  return patch;
}

export const sameProfile = (a: Profile, b: Profile) => Object.keys(touchedFields(a, b)).length === 0;
