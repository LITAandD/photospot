/** 네이티브 폰트: theme.ts가 쓰는 네 가족(display·body·medium·semibold)만 싣는다.
 * 번들이 실행되자마자 읽기 시작하고, 늦어도 첫 화면을 계속 막지 않는다(시스템 폰트로 먼저 그린다). */
import { GowunBatang_700Bold } from "@expo-google-fonts/gowun-batang/700Bold";
import { IBMPlexSansKR_400Regular } from "@expo-google-fonts/ibm-plex-sans-kr/400Regular";
import { IBMPlexSansKR_500Medium } from "@expo-google-fonts/ibm-plex-sans-kr/500Medium";
import { IBMPlexSansKR_600SemiBold } from "@expo-google-fonts/ibm-plex-sans-kr/600SemiBold";
import { isLoaded, loadAsync } from "expo-font";
import { useEffect, useState } from "react";

const FONTS = { GowunBatang_700Bold, IBMPlexSansKR_400Regular, IBMPlexSansKR_500Medium, IBMPlexSansKR_600SemiBold };
/** 앱 번들에 든 폰트는 보통 수십 ms에 끝난다. 그 이상 걸리면 기다리지 않는다. */
export const FIRST_FRAME_BUDGET_MS = 1500;
// 루트 레이아웃이 마운트될 때는 대개 끝나 있도록 모듈 평가 시점에 시작한다.
const ready = loadAsync(FONTS).catch(() => undefined);

export function useAppFonts(): boolean {
  const [done, setDone] = useState(() => Object.keys(FONTS).every(isLoaded));
  useEffect(() => {
    if (done) return;
    let active = true;
    const timer = setTimeout(() => { if (active) setDone(true); }, FIRST_FRAME_BUDGET_MS);
    ready.then(() => { if (active) setDone(true); });
    return () => { active = false; clearTimeout(timer); };
  }, [done]);
  return done;
}
