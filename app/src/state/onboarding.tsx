import type { Profile, ProfileOut } from "@photospot/client";
import React, { createContext, useContext, useReducer } from "react";

export interface Draft {
  profile: Profile;
  /** 설정에서 기존 프로필을 수정 중이면 불러온 원래 값 (건너뛰기가 기존 값을 지우지 않게) */
  original: Profile | null;
}

export const initialDraft: Draft = {
  original: null,
  profile: { gender: "undisclosed", birth_year: null, height_cm: null, pc_season: null, pc_subtone: null, body_type: null, mbti: null },
};

export type Action =
  | { type: "profile"; patch: Partial<Profile> }
  | { type: "reset" }
  | { type: "load"; profile: ProfileOut };

export function reducer(d: Draft, a: Action): Draft {
  switch (a.type) {
    case "profile": return { ...d, profile: { ...d.profile, ...a.patch } };
    case "reset": return initialDraft;
    case "load": {
      const profile: Profile = {
        gender: a.profile.gender, birth_year: a.profile.birth_year, height_cm: a.profile.height_cm,
        pc_season: a.profile.pc_season, pc_subtone: a.profile.pc_subtone, body_type: a.profile.body_type, mbti: a.profile.mbti,
      };
      return { ...initialDraft, profile, original: profile };
    }
  }
}

/** 가입 가능한 가장 늦은 출생연도 = 한국 시각 기준 올해 − 14 (만 14세 미만 아동의 개인정보는 처리하지 않는다. 서버 Profile.birth_year와 같은 기준) */
export const maxBirthYear = () => new Date(Date.now() + 9 * 3600 * 1000).getUTCFullYear() - 14;

/** Initial onboarding saves only the selected profile. */
export function toOnboarding(d: Draft) {
  const year = d.profile.birth_year, height = d.profile.height_cm;
  if (year != null && (!Number.isInteger(year) || year < 1900 || year > maxBirthYear())) {
    throw new Error(`출생연도는 1900년부터 ${maxBirthYear()}년 사이로 입력해 주세요. 만 14세 이상만 이용할 수 있어요`);
  }
  if (height != null && (!Number.isFinite(height) || height < 100 || height > 230)) {
    throw new Error("키는 100~230cm 사이로 입력해 주세요");
  }
  return {
    profile: { ...d.profile, pc_subtone: d.profile.pc_season ? d.profile.pc_subtone : null },
  };
}

const Ctx = createContext<{ draft: Draft; dispatch: React.Dispatch<Action> } | null>(null);

export function OnboardingProvider({ children }: { children: React.ReactNode }) {
  const [draft, dispatch] = useReducer(reducer, initialDraft);
  return <Ctx.Provider value={{ draft, dispatch }}>{children}</Ctx.Provider>;
}

export function useOnboarding() {
  const v = useContext(Ctx);
  if (!v) throw new Error("OnboardingProvider 안에서만 쓸 수 있어요");
  return v;
}
