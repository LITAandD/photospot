import { GowunBatang_700Bold } from "@expo-google-fonts/gowun-batang/700Bold";
import { IBMPlexSansKR_400Regular } from "@expo-google-fonts/ibm-plex-sans-kr/400Regular";
import { IBMPlexSansKR_500Medium } from "@expo-google-fonts/ibm-plex-sans-kr/500Medium";
import { IBMPlexSansKR_600SemiBold } from "@expo-google-fonts/ibm-plex-sans-kr/600SemiBold";
import { FontDisplay, useFonts } from "expo-font";
import { useEffect } from 'react';

export function useAppFonts(): boolean {
  useFonts({
    GowunBatang_700Bold: { uri: GowunBatang_700Bold, display: FontDisplay.SWAP },
    IBMPlexSansKR_400Regular: { uri: IBMPlexSansKR_400Regular, display: FontDisplay.SWAP },
    IBMPlexSansKR_500Medium: { uri: IBMPlexSansKR_500Medium, display: FontDisplay.SWAP },
    IBMPlexSansKR_600SemiBold: { uri: IBMPlexSansKR_600SemiBold, display: FontDisplay.SWAP },
  });
  useEffect(() => { document.documentElement.lang = 'ko'; }, []);
  // Large Korean font files are cached assets, but must never block first use.
  // The theme's system fallback displays text immediately on slow/offline loads.
  return true;
}
