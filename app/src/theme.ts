/** LIT A&D homepage palette, verified 2026-10-30: ivory, cyan and orange.
 * Bright brand fills use dark text; deeper variants keep links and controls legible.
 */
import { Platform } from 'react-native';
export const colors = {
  bg: "#FCF5EF", card: "#FFFFFF", line: "#E4DAD2", lineStrong: "#8D8178",
  ink: "#24211F", muted: "#665D56",
  accent: "#00C3FF", onAccent: "#24211F", accentSoft: "#E2F7FD", accentInk: "#006580", accentBorder: "#007B9E",
  secondary: "#FE7235", onSecondary: "#24211F", secondarySoft: "#FFE8DC", secondaryInk: "#9F3712",
  terracotta: "#AC422E", divider: "#F1E9E2",
};
const family = (name: string, fallback = 'system-ui, sans-serif') => Platform.OS === 'web' ? `${name}, ${fallback}` : name;
export const fonts = { display: family("IBMPlexSansKR_600SemiBold"), body: family("IBMPlexSansKR_400Regular"), medium: family("IBMPlexSansKR_500Medium"), semibold: family("IBMPlexSansKR_600SemiBold") };
export const radius = { control: 14, card: 22, button: 16 };
