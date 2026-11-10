import type { TokenStore } from '@photospot/client';

const listeners = new Set<(signedIn: boolean) => void>();
export const onSessionChange = (listener: (signedIn: boolean) => void) => {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
};

/** Notify the root gate after storage succeeds. No credentials in events. */
export function observableTokens(store: TokenStore): TokenStore {
  return {
    get: () => store.get(),
    async set(tokens) { await store.set(tokens); listeners.forEach(fn => fn(true)); },
    async clear() { await store.clear(); listeners.forEach(fn => fn(false)); },
  };
}

// --- 로그인 뒤 돌아갈 딥링크 --------------------------------------------------
// 비로그인 상태로 /place/<id>·/diagnosis/* 등을 열면 보호 구간이 /login으로 보낸다. 가려던 주소를 기억해 두었다가
// 로그인(프로필이 있으면)·온보딩 완료 뒤 /home 대신 그 화면으로 돌아간다. 웹은 OAuth 왕복·새로고침을 견디도록
// sessionStorage(탭 단위), 앱은 메모리(실행 단위)에만 둔다. 알려진 SPA 경로만 받아 외부 주소로 보내지 않는다.
const INTENDED_KEY = 'photospot.intended-route';
const DEEP_LINK = /^\/(place\/[^/?#]+|feedback\/[^/?#]+|diagnosis\/(personal-color|body-type)|home|saju|saved|settings|result|support|accounts)(\?[^#]*)?$/;
let intendedMemory: string | null = null;
const session = () => { try { return typeof sessionStorage === 'undefined' ? null : sessionStorage; } catch { return null; } };

export const isDeepLinkRoute = (href: string): boolean => DEEP_LINK.test(href) && href.length <= 2000;

/** 기억할 만한 주소면 저장하고 true. 로그인·온보딩·대문 등은 기억하지 않는다 */
export function rememberIntendedRoute(href: string): boolean {
  if (!isDeepLinkRoute(href)) return false;
  intendedMemory = href;
  try { session()?.setItem(INTENDED_KEY, href); } catch { /* 메모리에만 유지 */ }
  return true;
}

export function peekIntendedRoute(): string | null {
  let value = intendedMemory;
  if (!value) { try { value = session()?.getItem(INTENDED_KEY) ?? null; } catch { value = null; } }
  return value && isDeepLinkRoute(value) ? value : null;
}

export function clearIntendedRoute(): void {
  intendedMemory = null;
  try { session()?.removeItem(INTENDED_KEY); } catch { /* 이미 없음 */ }
}

/** 기억한 주소를 한 번만 꺼낸다 (꺼내면서 지운다) */
export function takeIntendedRoute(): string | null {
  const value = peekIntendedRoute();
  clearIntendedRoute();
  return value;
}

/** 앱 스킴(photospot://place/x)·웹 주소(https://…/place/x?date=…)를 라우터 경로로 바꾼다. 못 읽으면 null */
export function hrefFromUrl(url: string | null | undefined): string | null {
  if (!url) return null;
  const match = /^([a-z][a-z0-9+.-]*):\/\/([^/?#]*)(\/[^?#]*)?(\?[^#]*)?/i.exec(url);
  if (!match) return url.startsWith('/') ? url.split('#')[0] : null;
  const scheme = match[1].toLowerCase();
  let path = match[3] ?? '';
  // 앱 스킴은 호스트 자리부터 경로다 (photospot://place/x). Expo Go 개발 주소는 `--/` 뒤부터가 앱 경로다
  if (!['http', 'https', 'exp', 'exps'].includes(scheme)) path = `/${match[2]}${path}`;
  const dev = path.indexOf('/--/');
  if (dev >= 0) path = path.slice(dev + 3);
  if (!path.startsWith('/')) path = `/${path}`;
  return path + (match[4] ?? '');
}
