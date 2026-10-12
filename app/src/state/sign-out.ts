/** 로그아웃·만료 시 이동할 화면. 이동은 _layout의 onSignedOut 구독이 한 번만 한다 (탈퇴 후에는 첫 화면으로) */
type Route = "/" | "/login";
let next: Route = "/login";
export const signOutTo = (route: Route) => { next = route; };
export const takeSignOutRoute = (): Route => { const route = next; next = "/login"; return route; };
