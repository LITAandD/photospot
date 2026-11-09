/**
 * 정책 문서 주소. 웹 빌드는 scripts/build-web-preview.cjs가 같은 도메인의 /policies/*.html을 기본값으로 넣고,
 * 스토어 빌드는 .env의 절대 HTTPS 주소를 쓴다 (release-config.cjs가 네 주소와 문의 연락처를 요구한다).
 * EXPO_PUBLIC_* 값은 빌드 시점에 직접 참조한 식만 치환되므로 키마다 적는다.
 */
export const POLICY_URLS = {
  privacy: process.env.EXPO_PUBLIC_PRIVACY_URL ?? "",
  terms: process.env.EXPO_PUBLIC_TERMS_URL ?? "",
  location: process.env.EXPO_PUBLIC_LOCATION_TERMS_URL ?? "",
  deletion: process.env.EXPO_PUBLIC_ACCOUNT_DELETION_URL ?? "",
};

export const POLICY_LABELS: Record<keyof typeof POLICY_URLS, string> = {
  privacy: "개인정보 처리방침", terms: "서비스 이용약관", location: "위치정보 이용약관", deletion: "계정 삭제 안내",
};

/** 고객 문의 연락처. 비어 있으면 화면에 문의 줄을 표시하지 않는다 */
export const SUPPORT_EMAIL = process.env.EXPO_PUBLIC_SUPPORT_EMAIL ?? "";
