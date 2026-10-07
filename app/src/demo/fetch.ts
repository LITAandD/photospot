/** Browser-local profile, shared Python calculations and the imported real place DB. */
import type { AppFeedback, Profile, ProfileOut, SajuOut, PlaceDetail, RecommendationList, TypeCard } from "@photospot/client";
import fixtures from "./fixtures.json";
import { diagnose } from "./diagnose";

type Json = Record<string, unknown>;
type SavedSaju = Pick<SajuOut, "percents" | "dominant_element">;
type State = { profile: ProfileOut | null; saju: SavedSaju | null; bookmarks: string[]; feedback: Record<string, unknown>; appFeedback?: AppFeedback[] };
const KEY = "photospot.personal-preview.v1";
const EMPTY: Profile = { gender: "undisclosed", birth_year: null, height_cm: null, pc_season: null, pc_subtone: null, body_type: null, mbti: null };
let memory: State = { profile: null, saju: null, bookmarks: [], feedback: {} };
let generation = 0;
function load(): State {
  try { const data = localStorage.getItem(KEY); return data ? JSON.parse(data) : memory; } catch { return memory; }
}
function save(state: State) {
  localStorage.setItem(KEY, JSON.stringify(state));
  memory = state;
}
const json = (body: unknown, status = 200) => new Response(JSON.stringify(body), { status, headers: { "Content-Type": "application/json" } });
const problem = (status: number, title: string) => json({ type: "about:blank", title, status }, status);
const noContent = () => new Response(null, { status: 204 });
const today = () => new Date(Date.now() + 9 * 3600 * 1000).toISOString().slice(0, 10);
const server = (process.env.EXPO_PUBLIC_PREVIEW_API_URL ?? "").replace(/\/$/, "");
async function compute(path: string, body: unknown, signal?: AbortSignal | null) {
  try {
    return await fetch(`${server}/preview/${path}`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), signal });
  } catch (error) {
    if (signal?.aborted) throw error;
    return problem(503, "계산 서버에 연결하지 못했어요. 잠시 후 다시 시도해 주세요.");
  }
}
type Evaluation = { card: TypeCard; recommendations: RecommendationList; places: Record<string, PlaceDetail> };

export const demoFetch: typeof fetch = async (input, init) => {
  const url = new URL(typeof input === "string" ? input : (input as Request).url);
  const method = (init?.method ?? "GET").toUpperCase();
  const path = url.pathname;
  const body = init?.body && typeof init.body === "string" ? JSON.parse(init.body) as Json : {};
  const state = load();
  const version = generation;
  const profile = (): ProfileOut => ({ ...EMPTY, ...state.profile, profile_exists: !!state.profile,
    saju_enabled: !!state.saju, saju_element: state.saju?.dominant_element ?? null, saju_percents: state.saju?.percents ?? null });
  const evaluate = () => compute("evaluate", {
    profile: state.profile ?? EMPTY, element: state.saju?.dominant_element ?? null, percents: state.saju?.percents ?? null,
    visit_date: url.searchParams.get("date") ?? today(), use_saju: url.searchParams.get("use_saju") === "true",
    lat: Number(url.searchParams.get("lat") ?? 37.5796), lng: Number(url.searchParams.get("lng") ?? 126.977),
    radius_m: Number(url.searchParams.get("radius_m") ?? 5000), time_slot: url.searchParams.get("time_slot"),
    place_group: url.searchParams.get("place_group") ?? "all",
    place_ids: path === "/v1/me/bookmarks" ? state.bookmarks : path.startsWith("/v1/places/") ? [path.split("/")[3]] : [],
  }, init?.signal);

  if (path === '/v1/auth/providers') return json({providers:[],development:true});
  if (path === '/v1/me/session') return json({user_id:'local-personal-preview',is_admin:true,instagram_configured:false,billing_configured:false,ai_configured:false});
  if (path === '/v1/me/billing') return json({user_id:'local-personal-preview',premium:false,premium_until:null,management_url:null,configured:false});
  if (path === '/v1/me/instagram') return json(null);
  if (path === '/v1/sponsorships' || path === '/v1/admin/triages' || path === '/v1/admin/campaigns') return json([]);
  if (path === '/v1/feedback' && method === 'POST') {
    const message=String(body.message??'').trim(), category=String(body.category);
    if(message.length<5||message.length>2000||!['bug','idea','place','other'].includes(category)) return problem(422,'입력값을 확인해 주세요');
    const list=state.appFeedback??[];
    if(list.filter(f=>Date.now()-Date.parse(f.created_at)<86400000).length>=5) return problem(429,'의견은 하루 5건까지 보낼 수 있어요');
    const item:AppFeedback={id:crypto.randomUUID(),category:category as AppFeedback['category'],message,ai_consent:body.ai_consent===true,reviewed_text:null,created_at:new Date().toISOString()};
    save({...state,appFeedback:[item,...list]});return json(item,201);
  }
  if(path==='/v1/me/feedback'||path==='/v1/admin/feedback') return json(state.appFeedback??[]);
  if(path.startsWith('/v1/me/feedback/')&&method==='DELETE') {save({...state,appFeedback:(state.appFeedback??[]).filter(f=>f.id!==path.split('/').pop())});return noContent();}
  if(path.startsWith('/v1/admin/feedback/')&&method==='PATCH') {
    const id=path.split('/').pop(),text=String(body.reviewed_text??'').trim();
    if(text.length<5||text.length>2000) return problem(422,'검토 내용을 확인해 주세요');
    if(!(state.appFeedback??[]).some(f=>f.id===id&&f.ai_consent))return problem(409,'동의한 의견만 검토할 수 있어요');
    save({...state,appFeedback:(state.appFeedback??[]).map(f=>f.id===id?{...f,reviewed_text:text}:f)});return noContent();
  }
  if (path.startsWith('/v1/admin/') || path==='/v1/me/billing/sync' || path==='/v1/me/instagram/authorize') return problem(503,'체험 모드에서는 외부 서비스에 연결하지 않아요');
  if (path.startsWith("/v1/auth/")) {
    if (path.endsWith("/logout")) { generation += 1; return noContent(); }
    return json({ access_token: "personal-preview-access", refresh_token: "personal-preview-refresh", token_type: "bearer", expires_in: 3600,
      user_id: "local-personal-preview", is_new: !state.profile, profile_exists: !!state.profile });
  }
  if (path === "/v1/me/profile" && method === "PUT") {
    const response = await compute("profile", body, init?.signal);
    if (!response.ok) return response;
    const value = await response.json();
    if (version !== generation) return problem(401, "세션이 종료됐어요");
    state.profile = value; save({ ...load(), profile: value }); return json(profile());
  }
  if (path === "/v1/me/profile") return json(profile());
  if (path === "/v1/me/type-card") return compute("type-card", state.profile ?? EMPTY, init?.signal);
  if (path === "/v1/me/saju" && method === "PUT") {
    const response = await compute("saju", body, init?.signal);
    if (!response.ok) return response;
    const result: SajuOut = await response.json();
    if (version !== generation) return problem(401, "세션이 종료됐어요");
    // Never persist raw birth data, pillars, or the request body.
    state.saju = { percents: result.percents, dominant_element: result.dominant_element }; save({ ...load(), saju: state.saju });
    return json(result);
  }
  if (path === "/v1/me/saju" && method === "DELETE" || path === "/v1/me/consents/saju" && method === "DELETE") {
    state.saju = null; save(state); return noContent();
  }
  if (path === "/v1/me/consents/style_profile" && method === "DELETE") { state.profile = null; save(state); return noContent(); }
  if (path === "/v1/me/consents" || path.startsWith("/v1/me/consents/")) return noContent();
  if (path === "/v1/me/identities") return json([]);
  if (path === "/v1/me" && method === "DELETE") {
    generation += 1;
    localStorage.removeItem(KEY); memory = { profile: null, saju: null, bookmarks: [], feedback: {} }; return noContent();
  }
  if (path.startsWith("/v1/me/bookmarks/")) {
    const id = path.split("/").pop()!;
    if (method === "PUT") state.bookmarks = [...new Set([...state.bookmarks, id])];
    else state.bookmarks = state.bookmarks.filter((v) => v !== id);
    save(state); return noContent();
  }
  if (["/v1/me/type-card", "/v1/recommendations", "/v1/me/bookmarks"].includes(path) || path.startsWith("/v1/places/")) {
    const response = await evaluate();
    if (!response.ok) return response;
    const result: Evaluation = await response.json();
    if (path === "/v1/me/type-card") return json(result.card);
    if (path === "/v1/me/bookmarks") return json(state.bookmarks.filter((id) => result.places[id]).map((id) => ({ place_id: id, name: result.places[id].name, address: result.places[id].address, cover_photo: result.places[id].photos[0] ?? null })));
    if (path === "/v1/recommendations") return json(result.recommendations);
    const place = result.places[path.split("/")[3]];
    return place ? json(place) : problem(404, "장소 정보를 찾을 수 없어요");
  }
  if (/^\/v1\/recommendations\/\d+\/feedback$/.test(path)) {
    state.feedback[path.split("/")[3]] = body; save(state); return json({ ok: true }, 201);
  }
  if (path === "/v1/photos") return problem(501, "체험 모드에서는 사진을 서버에 저장하지 않아요. 사진 없이 후기를 보낼 수 있어요.");
  const match = path.match(/^\/v1\/diagnosis\/(personal-color|body-type)(\/questions)?$/);
  if (match) return match[2] ? json((fixtures.diagnosis_questions as Record<string, unknown>)[match[1]]) : diagnose(match[1], (body.answers as number[]) ?? []);
  return problem(404, `체험 모드에 없는 요청: ${method} ${path}`);
};
