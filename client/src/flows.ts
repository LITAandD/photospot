/**
 * 화면 단위 흐름: 앱 화면 하나가 여러 API를 순서대로 부를 때 쓰는 함수들.
 * (프레임워크 무관. React Native 훅에서는 이 함수들을 감싸기만 하면 된다)
 */
import { ApiError, type FeedbackIn, type PhotoSpotClient, type Profile, type UploadFile } from "./client.js";

export interface OnboardingDraft {
  profile: Profile;                 // 기본 정보·스타일·MBTI. 사주는 촬영 조건에서 별도로 선택.
}

/** 초기 입력 완료 → 프로필 저장 → 결과 카드. 저장된 오행은 변경하지 않는다. */
export async function finishOnboarding(client: PhotoSpotClient, draft: OnboardingDraft) {
  await client.grantConsent("style_profile");
  await client.putProfile(draft.profile);
  const card = await client.getTypeCard();
  return { card };
}

/** 6번 추천 목록 */
export function loadHome(client: PhotoSpotClient, lat: number, lng: number, date?: string) {
  return client.getRecommendations({ lat, lng, date, radiusM: 5000 });
}

export interface VisitReport {
  recommendationId: number;
  rating?: number;
  visited?: boolean;
  corrections?: Record<string, string>;   // 8번 화면 칩 → 예: { lighting: "warm_artificial" }
  photo?: { spotId: string; file: UploadFile };
}

/**
 * 8번 방문 후기 '보내기'. 사진이 있으면 먼저 올리고(동의 없으면 'consent_required') 후기에 연결한다.
 */
export async function submitVisit(client: PhotoSpotClient, report: VisitReport) {
  let photoId: string | undefined;
  let photoStatus: "uploaded" | "consent_required" | "skipped" = "skipped";
  if (report.photo) {
    try {
      const accepted = await client.uploadPhoto(report.photo.spotId, report.photo.file);
      photoId = accepted.photo_id;
      photoStatus = "uploaded";
    } catch (e) {
      if (e instanceof ApiError && e.forbidden) photoStatus = "consent_required";
      else throw e;
    }
  }
  const body: FeedbackIn = {
    rating: report.rating ?? null,
    visited: report.visited ?? null,
    photo_id: photoId ?? null,
    tag_corrections: report.corrections && Object.keys(report.corrections).length ? report.corrections : null,
  };
  await client.sendFeedback(report.recommendationId, body);
  return { photoStatus };
}

/** 3-1 · 3-2 자가진단: 문항을 받아 답하면 결과와 함께 프로필에 넣을 값을 돌려준다 */
export async function runDiagnosis(client: PhotoSpotClient, kind: "personal-color" | "body-type", answers: number[]) {
  const result = await client.diagnose(kind, answers);
  const patch: Partial<Profile> = kind === "personal-color"
    ? { pc_season: result.result as Profile["pc_season"] }
    : { body_type: result.result as Profile["body_type"] };
  return { result, patch };
}
