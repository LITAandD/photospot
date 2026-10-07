/** 웹: 글꼴 파일 대신 Google Fonts 스타일시트 (단일 HTML로 내보낼 때도 동작) */
import { useEffect, useState } from "react";

const HREF = "https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap";

export function useAppFonts(): boolean {
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (!document.querySelector(`link[href="${HREF}"]`)) {
      const link = document.createElement("link");
      link.rel = "stylesheet"; link.href = HREF;
      document.head.appendChild(link);
    }
    const style = document.createElement("style");
    // 굵기별 이름을 CSS 글꼴로 연결
    style.textContent = `
      [style*="GowunBatang_700Bold"] { font-family: "Gowun Batang", serif !important; font-weight: 700 !important; }
      [style*="IBMPlexSansKR_400Regular"] { font-family: "IBM Plex Sans KR", sans-serif !important; font-weight: 400 !important; }
      [style*="IBMPlexSansKR_500Medium"] { font-family: "IBM Plex Sans KR", sans-serif !important; font-weight: 500 !important; }
      [style*="IBMPlexSansKR_600SemiBold"] { font-family: "IBM Plex Sans KR", sans-serif !important; font-weight: 600 !important; }`;
    document.head.appendChild(style);
    setReady(true);
  }, []);
  return ready;
}
