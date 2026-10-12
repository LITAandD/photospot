/** 디자인 캔버스 '갤러리 에디토리얼' 룩과 같은 값 */
import { Platform } from 'react-native';
export const colors = {
  bg: "#F6F3EE", card: "#FFFFFF", line: "#E3DDD3", lineStrong: "#82786A",
  ink: "#1F1D1A", muted: "#5E5A53", accent: "#3F5E78", accentSoft: "#EEF2F5", accentInk: "#2C4459",
  terracotta: "#A9573C", divider: "#EFEAE2",
};
const family = (name: string, fallback = 'system-ui, sans-serif') => Platform.OS === 'web' ? `${name}, ${fallback}` : name;
export const fonts = { display: family("GowunBatang_700Bold", 'Georgia, serif'), body: family("IBMPlexSansKR_400Regular"), medium: family("IBMPlexSansKR_500Medium"), semibold: family("IBMPlexSansKR_600SemiBold") };
export const radius = { control: 12, card: 16, button: 14 };
