import { GowunBatang_700Bold } from "@expo-google-fonts/gowun-batang/700Bold";
import { IBMPlexSansKR_400Regular } from "@expo-google-fonts/ibm-plex-sans-kr/400Regular";
import { IBMPlexSansKR_500Medium } from "@expo-google-fonts/ibm-plex-sans-kr/500Medium";
import { IBMPlexSansKR_600SemiBold } from "@expo-google-fonts/ibm-plex-sans-kr/600SemiBold";
import { useFonts } from "expo-font";

export function useAppFonts(): boolean {
  const [loaded, error] = useFonts({ GowunBatang_700Bold, IBMPlexSansKR_400Regular, IBMPlexSansKR_500Medium, IBMPlexSansKR_600SemiBold });
  return loaded || !!error;
}
