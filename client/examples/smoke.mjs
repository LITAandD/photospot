import { PhotoSpotClient, ApiError, finishOnboarding, loadHome, submitVisit, runDiagnosis } from "./dist/index.js";
import { readFile } from "node:fs/promises";

const client = new PhotoSpotClient({ baseUrl: "http://localhost:8001", getToken: () => process.env.TOKEN });
console.log("health", await client.health());

// 3-1 자가진단 → 프로필 값
const diag = await runDiagnosis(client, "personal-color", [1, 1, 1, 0, 0, 2]);
console.log("diagnosis", diag.result.result_label, diag.result.confidence, "→ patch", diag.patch);

// 2·3·4번 화면 → 5번 결과 카드
const { card, saju } = await finishOnboarding(client, {
  profile: { gender: "female", height_cm: 162, ...diag.patch, pc_subtone: "light", body_type: "wave", mbti: "INFP" },
  saju: { birth_date: "1998-05-14", birth_time: "14:30:00", calendar: "solar", leap_month: false },
});
console.log("saju", saju.dominant_label, saju.pillars.day.hangul + "일", saju.corrections);
console.log("card", card.name, "|", card.best_light.join(", "));

// 6번 추천 목록 (경복궁 근처, 10월 10일)
const home = await loadHome(client, 37.5796, 126.977, "2026-10-10");
console.log("home", home.items.map(i => `${i.place_name} ${i.score} (${i.time_slot_label})`));
const top = home.items[0];

// 7번 상세
const place = await client.getPlace(top.place_id, "2026-10-10");
console.log("detail", place.name, place.best_scene?.score, place.tips.map(t => t.label), place.visit_notes[0]);

// 8번 후기: 동의 전 업로드 → consent_required, 동의 후 → uploaded
const file = new File([await readFile("./smoke.jpg")], "me.jpg", { type: "image/jpeg" });
let r = await submitVisit(client, { recommendationId: top.recommendation_id, rating: 5, visited: true, photo: { spotId: place.best_scene.scene_id && "20000000-0000-0000-0000-000000000002", file } });
console.log("visit before consent", r.photoStatus);
await client.grantConsent("photo_analysis");
r = await submitVisit(client, { recommendationId: top.recommendation_id, rating: 5, visited: true, corrections: { lighting: "warm_artificial" }, photo: { spotId: "20000000-0000-0000-0000-000000000002", file } });
console.log("visit after consent", r.photoStatus);

// 오류 형태
try { await client.getRecommendations({ lat: 51.5, lng: -0.1 }); } catch (e) { console.log("error", e instanceof ApiError, e.status, e.title); }
try { await new PhotoSpotClient({ baseUrl: "http://localhost:8001", getToken: () => null }).getProfile(); } catch (e) { console.log("no token", e.status, e.unauthorized); }
