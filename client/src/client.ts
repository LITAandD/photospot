/**
 * 포토스팟 API 클라이언트 (React Native · 웹 공용, fetch 기반, 의존성 없음)
 *
 * 타입은 openapi.yaml에서 생성한 ./api.d.ts 를 쓴다:
 *   npx openapi-typescript ../openapi.yaml -o src/api.d.ts
 */
import type { components } from "./api.js";

type S = components["schemas"];
export type Profile = S["Profile"];
export type Bookmark = S["Bookmark"];
export type ProfileOut = S["ProfileOut"];
export type SajuIn = S["SajuIn"];
export type SajuOut = S["SajuOut"];
export type TypeCard = S["TypeCard"];
export type ConsentType = S["ConsentIn"]["type"];
export type RecommendationList = S["RecommendationList"];
export type RecommendationItem = S["RecommendationItem"];
export type PlaceDetail = S["PlaceDetail"];
export type ScoreExplanation = S["ScoreExplanation"];
export type ScoreWeight = S["ScoreWeight"];
export type FeedbackIn = S["FeedbackIn"];
export type PhotoAccepted = S["PhotoAccepted"];
export type DiagnosisQuestion = S["DiagnosisQuestion"];
export type DiagnosisOut = S["DiagnosisOut"];
export type ReviewItem = S["ReviewItem"];
export type SceneEdit = S["SceneEdit"];
export type TimeSlot = RecommendationItem["time_slot"];
export type PlaceGroup = NonNullable<RecommendationList["place_group"]>;
export type DiagnosisKind = "personal-color" | "body-type";
export type TokenPair = S["TokenPair"];
export type LoginIn = S["LoginIn"];
export type DeleteAccountIn = S["DeleteAccountIn"];
export type IdentityOut = S["IdentityOut"];
export type AuthProvider = IdentityOut["provider"];
export type AppFeedback = { id: string; category: 'bug'|'idea'|'place'|'other'; message: string; ai_consent: boolean; reviewed_text: string|null; created_at: string };
export type BillingStatus = { user_id: string; premium: boolean; configured: boolean; premium_until: string|null; management_url: string|null };
export type GrowthSession = { user_id: string; is_admin: boolean; instagram_configured: boolean; billing_configured: boolean; ai_configured: boolean };
export type Campaign = { id: string; place_id: string; sponsor: string; headline: string; placement: 'banner'|'priority'; starts_at: string; ends_at: string; approved: boolean; impressions?: number; clicks?: number };
export type SponsoredPlace = Campaign & { place_name: string; photo: S['Photo'] };
export type Triage = { id: string; status: 'proposed'|'approved'|'planned'|'done'|'dismissed'; review_note: string; result: { title: string; summary: string; impact: number; urgency: number; effort: number; reason: string; acceptance: string; reporters: number; priority_score: number; feedback_ids: string[] } };

/** 액세스·갱신 토큰 저장소 (앱: SecureStore, 웹: 메모리 + httpOnly 쿠키 등) */
export interface TokenStore {
  get(): Promise<{ access: string; refresh: string } | null> | { access: string; refresh: string } | null;
  set(tokens: { access: string; refresh: string }): Promise<void> | void;
  clear(): Promise<void> | void;
}

/** 서버 오류 (application/problem+json) */
export class ApiError extends Error {
  constructor(
    public readonly status: number,
    public readonly title: string,
    public readonly detail?: unknown,
  ) {
    super(`${status} ${title}`);
    this.name = "ApiError";
  }
  /** 로그인이 필요한 상황 */
  get unauthorized() { return this.status === 401; }
  /** 동의가 필요한 상황 (예: 사진 분석 동의 없이 업로드) */
  get forbidden() { return this.status === 403; }
}

/** React Native의 파일 객체 ({uri, name, type}) 또는 웹의 Blob/File */
export type UploadFile = Blob | { uri: string; name: string; type: string };

export interface ClientOptions {
  baseUrl: string;                                   // 예: https://api.example.com
  /** 토큰 저장소. 있으면 401일 때 갱신 토큰으로 한 번 재시도한다 */
  tokens?: TokenStore;
  /** (단순 사용) 저장된 액세스 토큰만 돌려준다. tokens가 있으면 무시 */
  getToken?: () => Promise<string | null> | string | null;
  /** 갱신까지 실패했을 때 (로그인 화면으로 보내기) */
  onSignedOut?: () => void;
  fetch?: typeof fetch;                              // 테스트·폴리필용
  timeoutMs?: number;
}

export interface RecommendationQuery {
  lat: number;
  lng: number;
  date?: string;                                     // YYYY-MM-DD (없으면 오늘, KST)
  radiusM?: number;                                  // 기본 5000, 최대 50000
  timeSlot?: TimeSlot;
  useSaju?: boolean;
  placeGroup?: PlaceGroup;
  limit?: number;
  photoOnly?: boolean;
  minFit?: number;
}

export class PhotoSpotClient {
  private readonly base: string;
  private readonly tokens?: TokenStore;
  private readonly getToken?: ClientOptions["getToken"];
  private readonly onSignedOut?: () => void;
  private readonly fetchImpl: typeof fetch;
  private readonly timeoutMs: number;
  private refreshing: Promise<boolean> | null = null;
  private sessionVersion = 0;

  constructor(opts: ClientOptions) {
    this.base = opts.baseUrl.replace(/\/+$/, "");
    this.tokens = opts.tokens;
    this.getToken = opts.getToken;
    this.onSignedOut = opts.onSignedOut;
    this.fetchImpl = opts.fetch ?? ((input, init) => fetch(input, init));   // 브라우저에서 this 바인딩 오류 방지
    this.timeoutMs = opts.timeoutMs ?? 15_000;
  }

  // --- 로그인 ----------------------------------------------------------------
  /** 각 서비스 SDK가 준 토큰으로 로그인. 성공하면 토큰 저장소에 저장한다 */
  readonly auth = {
    google: (idToken: string, nonce?: string) => this.login("google", { token: idToken, nonce: nonce ?? null, name: null }),
    apple: (identityToken: string, opts: { nonce?: string; name?: string; authorizationCode?: string } = {}) =>
      this.login("apple", { token: identityToken, nonce: opts.nonce ?? null, name: opts.name ?? null, authorization_code: opts.authorizationCode }),
    naver: (accessToken: string) => this.login("naver", { token: accessToken, nonce: null, name: null }),
    kakao: (accessToken: string) => this.login("kakao", { token: accessToken, nonce: null, name: null }),
    /** 이 기기의 갱신 토큰 무효화 + 저장소 비우기 */
    logout: async () => {
      this.sessionVersion += 1;
      const t = await this.tokens?.get();
      if (t) await this.request<void>("POST", "/v1/auth/logout", { body: { refresh_token: t.refresh }, auth: false }).catch(() => undefined);
      await this.tokens?.clear();
      this.onSignedOut?.();
    },
    /** 저장된 토큰이 있는지 (앱 시작 시 로그인 화면을 건너뛸지) */
    isSignedIn: async () => !!(await this.tokens?.get()),
  };

  private async login(provider: AuthProvider, body: LoginIn) {
    const version = ++this.sessionVersion;
    const pair = await this.request<TokenPair>("POST", `/v1/auth/${provider}`, { body, auth: false });
    if (version === this.sessionVersion) await this.tokens?.set({ access: pair.access_token, refresh: pair.refresh_token });
    return pair;
  }

  /** 갱신 토큰으로 새 토큰 쌍. 동시에 여러 요청이 401을 받아도 갱신은 한 번만 */
  private refreshTokens(): Promise<boolean> {
    if (!this.refreshing) {
      this.refreshing = (async () => {
        const version = this.sessionVersion;
        try {
          const t = await this.tokens?.get();
          if (!t) { this.onSignedOut?.(); return false; }
          const pair = await this.request<TokenPair>("POST", "/v1/auth/refresh", { body: { refresh_token: t.refresh }, auth: false });
          if (version !== this.sessionVersion) return false;
          await this.tokens?.set({ access: pair.access_token, refresh: pair.refresh_token });
          return true;
        } catch (error) {
          if (error instanceof ApiError && error.status === 401) {
            if (version === this.sessionVersion) {
              await this.tokens?.clear();
              this.onSignedOut?.();
            }
            return false;
          }
          // Offline/5xx does not mean the saved session has expired.
          throw error;
        } finally {
          this.refreshing = null;
        }
      })();
    }
    return this.refreshing;
  }

  identities() { return this.request<IdentityOut[]>("GET", "/v1/me/identities"); }
  authProviders() { return this.request<{ providers: AuthProvider[]; development: boolean }>('GET', '/v1/auth/providers', { auth: false }); }
  session() { return this.request<GrowthSession>('GET', '/v1/me/session'); }
  instagram() { return this.request<{ username: string; connected_at: string }|null>('GET', '/v1/me/instagram'); }
  connectInstagram() { return this.request<{ url: string }>('POST', '/v1/me/instagram/authorize'); }
  disconnectInstagram() { return this.request<void>('DELETE', '/v1/me/instagram'); }
  billing() { return this.request<BillingStatus>('GET', '/v1/me/billing'); }
  syncBilling() { return this.request<BillingStatus>('POST', '/v1/me/billing/sync', { timeoutMs: 35000 }); }
  submitAppFeedback(body: Pick<AppFeedback, 'category'|'message'|'ai_consent'>) { return this.request<AppFeedback>('POST', '/v1/feedback', { body }); }
  myAppFeedback() { return this.request<AppFeedback[]>('GET', '/v1/me/feedback'); }
  deleteAppFeedback(id: string) { return this.request<void>('DELETE', `/v1/me/feedback/${id}`); }
  adminFeedback() { return this.request<AppFeedback[]>('GET', '/v1/admin/feedback'); }
  reviewFeedback(id: string, reviewed_text: string) { return this.request<void>('PATCH', `/v1/admin/feedback/${id}`, { body: { reviewed_text } }); }
  triageFeedback(feedback_ids: string[]) { return this.request<{ created: number }>('POST', '/v1/admin/feedback/triage', { body: { feedback_ids }, timeoutMs: 40000 }); }
  adminTriages() { return this.request<Triage[]>('GET', '/v1/admin/triages'); }
  decideTriage(id: string, status: Exclude<Triage['status'],'proposed'>, note: string) { return this.request<void>('PATCH', `/v1/admin/triages/${id}`, { body: { status, note } }); }
  adminCampaigns() { return this.request<Campaign[]>('GET', '/v1/admin/campaigns'); }
  createCampaign(body: Omit<Campaign,'id'|'approved'>) { return this.request<{ id: string }>('POST', '/v1/admin/campaigns', { body }); }
  approveCampaign(id: string, approved: boolean) { return this.request<void>('PATCH', `/v1/admin/campaigns/${id}`, { body: { approved } }); }
  sponsorships(q: RecommendationQuery) { return this.request<SponsoredPlace[]>('GET', '/v1/sponsorships', { query: { lat:q.lat, lng:q.lng, radius_m:q.radiusM, place_group:q.placeGroup } }); }
  campaignEvent(id: string, kind: 'impression'|'click') { return this.request<void>('POST', `/v1/sponsorships/${id}/events`, { body: { kind } }); }
  linkIdentity(provider: AuthProvider, token: string, opts: { nonce?: string; name?: string; authorizationCode?: string } = {}) {
    return this.request<void>("POST", `/v1/me/identities/${provider}`, { body: { token, nonce: opts.nonce ?? null, name: opts.name ?? null, authorization_code: opts.authorizationCode } });
  }
  unlinkIdentity(provider: AuthProvider, body?: DeleteAccountIn) { return this.request<void>("DELETE", `/v1/me/identities/${provider}`, { body, timeoutMs: 35_000 }); }

  // --- 내 정보 --------------------------------------------------------------
  health() { return this.request<{ ok: boolean }>("GET", "/v1/health", { auth: false }); }
  getProfile() { return this.request<ProfileOut>("GET", "/v1/me/profile"); }
  putProfile(profile: Profile) { return this.request<ProfileOut>("PUT", "/v1/me/profile", { body: profile }); }
  grantConsent(type: ConsentType) { return this.request<void>("POST", "/v1/me/consents", { body: { type } }); }
  revokeConsent(type: ConsentType) { return this.request<void>("DELETE", `/v1/me/consents/${type}`); }
  /** 생년월일시는 서버가 계산 직후 폐기한다. consent: true 필수 */
  putSaju(input: SajuIn) { return this.request<SajuOut>("PUT", "/v1/me/saju", { body: input }); }
  deleteSaju() { return this.request<void>("DELETE", "/v1/me/saju"); }
  getTypeCard() { return this.request<TypeCard>("GET", "/v1/me/type-card"); }
  async deleteAccount(body?: DeleteAccountIn) {
    await this.request<void>("DELETE", "/v1/me", { body, timeoutMs: 35_000 });
    this.sessionVersion += 1;
    await this.tokens?.clear();
    this.onSignedOut?.();
  }
  getBookmarks() { return this.request<Bookmark[]>("GET", "/v1/me/bookmarks"); }
  saveBookmark(placeId: string) { return this.request<void>("PUT", `/v1/me/bookmarks/${placeId}`); }
  removeBookmark(placeId: string) { return this.request<void>("DELETE", `/v1/me/bookmarks/${placeId}`); }

  // --- 추천 ------------------------------------------------------------------
  getRecommendations(q: RecommendationQuery) {
    return this.request<RecommendationList>("GET", "/v1/recommendations", {
      query: { lat: q.lat, lng: q.lng, date: q.date, radius_m: q.radiusM, time_slot: q.timeSlot, limit: q.limit, use_saju: q.useSaju ?? false, place_group: q.placeGroup ?? "all", photo_only: q.photoOnly, min_fit: q.minFit },
    });
  }
  getPlace(placeId: string, date?: string, useSaju = false) {
    return this.request<PlaceDetail>("GET", `/v1/places/${placeId}`, { query: { date, use_saju: useSaju } });
  }
  sendFeedback(recommendationId: number, body: FeedbackIn) {
    return this.request<{ ok: boolean }>("POST", `/v1/recommendations/${recommendationId}/feedback`, { body });
  }

  // --- 사진 ------------------------------------------------------------------
  /** photo_analysis 동의가 없으면 ApiError(403). 서버가 위치·기기 정보를 지운다 */
  uploadPhoto(spotId: string, file: UploadFile) {
    const form = new FormData();
    form.append("spot_id", spotId);
    if (typeof Blob !== "undefined" && file instanceof Blob) {
      form.append("file", file, (file as { name?: string }).name ?? "photo.jpg");
    } else {
      // React Native FormData accepts {uri, name, type}; a filename argument is for Blob only.
      form.append("file", file as Blob);
    }
    return this.request<PhotoAccepted>("POST", "/v1/photos", { form });
  }

  // --- 자가진단 ----------------------------------------------------------------
  diagnosisQuestions(kind: DiagnosisKind) {
    return this.request<DiagnosisQuestion[]>("GET", `/v1/diagnosis/${kind}/questions`, { auth: false });
  }
  diagnose(kind: DiagnosisKind, answers: number[]) {
    return this.request<DiagnosisOut>("POST", `/v1/diagnosis/${kind}`, { body: { answers }, auth: false });
  }

  // --- 검수 (관리자 토큰 필요) --------------------------------------------------
  adminReviewQueue(limit = 50) {
    return this.request<ReviewItem[]>("GET", "/v1/admin/review-queue", { query: { limit } });
  }
  adminEditScene(sceneId: string, edit: SceneEdit) {
    return this.request<void>("PATCH", `/v1/admin/scenes/${sceneId}`, { body: edit });
  }

  // --- 내부 ------------------------------------------------------------------
  private async request<T>(
    method: string,
    path: string,
    opts: { query?: Record<string, unknown>; body?: unknown; form?: FormData; auth?: boolean; retried?: boolean; timeoutMs?: number } = {},
  ): Promise<T> {
    const url = new URL(this.base + path);
    for (const [k, v] of Object.entries(opts.query ?? {})) {
      if (v !== undefined && v !== null) url.searchParams.set(k, String(v));
    }
    const headers: Record<string, string> = { Accept: "application/json" };
    let sentToken: string | null = null;
    if (opts.auth !== false) {
      const token = this.tokens ? (await this.tokens.get())?.access ?? null : await this.getToken?.() ?? null;
      sentToken = token;
      if (token) headers.Authorization = `Bearer ${token}`;
    }
    let body: BodyInit | undefined;
    if (opts.form) {
      body = opts.form;                                // Content-Type은 fetch가 boundary와 함께 붙인다
    } else if (opts.body !== undefined) {
      headers["Content-Type"] = "application/json";
      body = JSON.stringify(opts.body);
    }
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), opts.timeoutMs ?? this.timeoutMs);
    try {
      const res = await this.fetchImpl(url.toString(), { method, headers, body, signal: controller.signal });
      if (res.status === 204) return undefined as T;
      const text = await res.text();
      let data: any = null;
      try { data = text ? JSON.parse(text) : null; } catch {
        if (res.ok) throw new ApiError(502, "서버 응답을 읽을 수 없어요");
      }
      if (res.status === 401 && opts.auth !== false && this.tokens && !opts.retried) {
        const current = await this.tokens.get();
        if ((current && current.access !== sentToken) || await this.refreshTokens()) {
          return this.request<T>(method, path, { ...opts, retried: true });
        }
      }
      if (!res.ok) {
        throw new ApiError(res.status, data?.title || res.statusText || "서버 요청을 처리하지 못했어요", data?.detail);
      }
      return data as T;
    } finally {
      clearTimeout(timer);
    }
  }
}
