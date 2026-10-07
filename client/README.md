# 포토스팟 앱 클라이언트 (`@photospot/client`)

React Native·웹 공용 TypeScript 클라이언트. 타입은 `openapi.yaml`에서 생성하므로 서버와 어긋나지 않는다.

```bash
npm run types    # openapi.yaml → src/api.d.ts (서버 명세가 바뀌면 다시)
npm run build    # dist/
```
Flutter를 쓴다면 같은 명세로 Dart 클라이언트를 만들면 된다: `openapi-generator generate -i openapi.yaml -g dart`.

## 시작
```ts
import { PhotoSpotClient } from "@photospot/client";
import * as SecureStore from "expo-secure-store";        // 토큰은 안전 저장소에

export const api = new PhotoSpotClient({
  baseUrl: "https://api.example.com",
  getToken: () => SecureStore.getItemAsync("jwt"),       // 로그인 서비스가 발급한 JWT
});
```
로그인 자체는 별도 인증 서비스(Firebase·Supabase·자체)가 맡고, 발급된 JWT만 넘기면 된다.

## 화면 ↔ API
| 화면 | 호출 | 비고 |
|---|---|---|
| 1 시작 | `health()` (선택) | |
| 2·3·4 프로필 입력 | 값을 앱 상태에 모아두기만 | 화면마다 저장하지 않고 4번 끝에 한 번에 |
| 3-1·3-2 자가진단 | `diagnosisQuestions(kind)` → `runDiagnosis(kind, answers)` | 결과의 `patch`를 프로필 초안에 합침 |
| 4 '추천 받기' | `finishOnboarding(client, draft)` | 프로필만 저장 → 결과 카드. 기존 오행은 유지 |
| 5 결과 카드 | `getTypeCard()` | 공유 카드 문구 전부 서버에서 옴 |
| 6 추천 목록 | `loadHome(client, lat, lng, date)` | 항목의 `recommendation_id`를 상세·후기까지 들고 감 |
| 촬영 날짜·선택 오행 | `putSaju(input)` → `getRecommendations({ date, useSaju: true, ... })` | 실제 생년월일 계산 후 선택한 날의 일진을 함께 반영. 기본값 false |
| 7 장소 상세 | `getPlace(placeId, date, useSaju)` | 목록과 같은 날짜·선택 여부를 전달 |
| 7 '네이버 지도' | `links.naver_map_url` 열기 | 영업시간은 `links.google_place_id`로 앱이 직접 Places 조회 |
| 8 방문 후기 | `submitVisit(client, report)` | 사진 있으면 업로드 후 후기 연결. 동의 없으면 `consent_required` |
| 동의 화면 | `grantConsent("photo_analysis")` | 사진 올리기 전에 한 번 |
| 설정 | `deleteSaju()`, `revokeConsent()`, `deleteAccount()` | |

## 오류 처리
모든 실패는 `ApiError`로 온다: `status`, `title`(사용자에게 그대로 보여줄 수 있는 문장), `detail`.
- `e.unauthorized` → 로그인 화면으로
- `e.forbidden` → 동의 화면으로 (사진 업로드)
- `422` → 입력값 확인 (예: 한국 밖 좌표, 음력 날짜 오류)

## React Native 예시 (6번 화면)
```tsx
function useHome(lat: number, lng: number, date?: string) {
  const [data, setData] = useState<RecommendationList | null>(null);
  const [error, setError] = useState<ApiError | null>(null);
  useEffect(() => {
    let alive = true;
    loadHome(api, lat, lng, date).then(d => alive && setData(d)).catch(e => alive && setError(e));
    return () => { alive = false; };
  }, [lat, lng, date]);
  return { data, error };
}
```
사진 업로드는 `{ uri, name, type }` 객체를 그대로 `uploadPhoto(spotId, file)`에 넘기면 된다 (React Native의 FormData 규약).

## 검증
`node /tmp/smoke.mjs` 같은 스크립트로 자가진단 → 온보딩 → 추천 → 상세 → 후기(동의 전/후) → 오류 형태까지 실제 서버에 대해 통과시켰다.
