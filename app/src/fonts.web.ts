/** 웹 폰트: 번들에 TTF 16.7MB를 싣는 대신 Google Fonts CSS(unicode-range 조각·display=swap)를 쓴다 (F004/S-6).
 *
 * theme.ts는 RN 방식 가족명(IBMPlexSansKR_400Regular 등)을 쓰므로 Google CSS의 @font-face 규칙을
 * 그 이름으로 복제해 넣는다. CSS는 CORS(ACAO:*)로 받으므로 crossorigin 링크면 cssRules를 읽을 수 있다.
 * 폰트가 늦거나 실패해도 시스템 폰트로 바로 그린다(첫 화면을 막지 않는다). */
import { useEffect } from 'react';

export const GOOGLE_FONTS_CSS = 'https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap';
/** Google 가족명 + 굵기 → theme.ts가 쓰는 가족명 */
export const FAMILY_ALIASES: Record<string, Record<number, string>> = {
  'Gowun Batang': { 700: 'GowunBatang_700Bold' },
  'IBM Plex Sans KR': { 400: 'IBMPlexSansKR_400Regular', 500: 'IBMPlexSansKR_500Medium', 600: 'IBMPlexSansKR_600SemiBold' },
};
const FAMILY = /font-family:\s*(["']?)([^;"']+)\1\s*;/;
const WEIGHT = /font-weight:\s*(\d+)/;
const STYLE_ID = 'app-font-aliases';
const LINK_ID = 'app-fonts';

/** Google CSS의 @font-face 규칙(조각마다 하나)을 RN 가족명으로 바꿔 쓴 CSS. unicode-range·display=swap·src는 그대로. */
export function aliasRules(rules: Iterable<{ cssText: string }>): string {
  const out: string[] = [];
  for (const rule of rules) {
    const text = rule.cssText;
    if (!text.startsWith('@font-face')) continue;
    const family = FAMILY.exec(text)?.[2]?.trim();
    const weight = Number(WEIGHT.exec(text)?.[1] ?? 400);
    const alias = family ? FAMILY_ALIASES[family]?.[weight] : undefined;
    if (!alias) continue;
    out.push(text.replace(FAMILY, `font-family: ${alias};`));
  }
  return out.join('\n');
}

function installAliases(link: HTMLLinkElement, doc: Document): boolean {
  let rules: CSSRuleList;
  try { rules = link.sheet!.cssRules; } catch { return false; }        // CORS 없이 받았으면 읽을 수 없다
  const css = aliasRules(Array.from(rules));
  if (!css) return false;
  let style = doc.getElementById(STYLE_ID) as HTMLStyleElement | null;
  if (!style) { style = doc.createElement('style'); style.id = STYLE_ID; doc.head.appendChild(style); }
  style.textContent = css;
  return true;
}

let pending: Promise<boolean> | null = null;
/** Google Fonts CSS를 한 번만 요청해 RN 가족명으로 등록한다. 실패하면 false(시스템 폰트 유지). */
export function loadWebFonts(doc: Document = document): Promise<boolean> {
  if (pending) return pending;
  pending = new Promise(resolve => {
    // 빌드가 index.html에 같은 id의 링크(crossorigin)를 미리 넣어 두면 그 링크를 그대로 쓴다.
    const existing = doc.getElementById(LINK_ID) as HTMLLinkElement | null;
    if (existing) {
      if (existing.sheet) return resolve(installAliases(existing, doc));
      existing.addEventListener('load', () => resolve(installAliases(existing, doc)));
      existing.addEventListener('error', () => resolve(false));
      return;
    }
    const preconnect = doc.createElement('link');
    preconnect.rel = 'preconnect'; preconnect.href = 'https://fonts.gstatic.com'; preconnect.crossOrigin = 'anonymous';
    const link = doc.createElement('link');
    link.id = LINK_ID; link.rel = 'stylesheet'; link.href = GOOGLE_FONTS_CSS; link.crossOrigin = 'anonymous';
    link.onload = () => resolve(installAliases(link, doc));
    link.onerror = () => resolve(false);
    doc.head.append(preconnect, link);
  });
  return pending;
}

// 번들이 실행되자마자 CSS 요청을 시작한다(마운트를 기다리지 않는다).
if (typeof document !== 'undefined') void loadWebFonts();

export function useAppFonts(): boolean {
  useEffect(() => { document.documentElement.lang = 'ko'; }, []);
  // display=swap: 시스템 폰트로 먼저 그리고 조각이 도착하는 대로 바뀐다. 첫 화면을 폰트 때문에 비우지 않는다.
  return true;
}
