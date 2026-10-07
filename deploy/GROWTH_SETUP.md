# 계정 연동·수익화·피드백 운영 설정

현재 구현은 설정 → SNS 계정 연결 / 개발자 후원·Plus / 의견 보내기에서 확인한다. 브라우저 체험 모드는 로그인·결제·AI 요청을 실제 성공으로 흉내 내지 않는다. 의견은 해당 브라우저에만 저장되고 로컬 관리 미리보기에서 검토할 수 있다. 실서비스에서는 모든 사용자 데이터와 권한을 PostgreSQL에서 확인한다.

## 배포 전 필수 작업

현재 서버·도메인·개발자 계정은 미준비 상태다. 아래 명령은 값/비밀키를 출력하지 않고 누락 항목을 모두 표시한다. 실패는 출시 준비가 덜 되었다는 뜻이며, `.env`를 자동으로 바꾸지 않는다.

```sh
# 루트: 서버 설정 검사. 네트워크 호출 없음
python -m scripts.check_release --env-file .env --growth
# 앱: .env.production 또는 배포 환경의 공개 설정 검사
npm --prefix app run check:release -- --growth
# 서버가 준비된 뒤, 해당 서버에서 환경변수 주입 후 DB 읽기 검사
python -m scripts.check_release --growth --database
```

`--growth`는 Instagram·RevenueCat·GPT를 포함한 이번 출시 범위를 검사한다. 기본 검사는 결제가 없는 출시에도 사용할 수 있다. 키의 존재나 형식이 맞는지 확인할 뿐 제공자 승인, 결제 상품 공개, 정책 내용의 적정성까지 인증하지 않는다. 비밀 값은 채팅에 보내지 않고 서비스별 비밀 저장소에 설정한다.

1. 스테이징 PostgreSQL/PostGIS에 기존 마이그레이션과 `017_product_growth.sql`을 `python -m scripts.migrate`로 적용한다. 공개 SQLite 장소 DB와 별개다. 신규 테이블은 의견, AI 개선안, 계정 연결, 구독 캐시, 광고·운영 기록이다.
2. 실제 HTTPS API·개인정보 처리방침·약관·탈퇴 주소, Apple/Google 배포 계정, EAS 프로젝트와 서명을 설정한다. `npm run check:release`가 성공해야 한다.
3. 아래 공급자 콘솔 설정과 비밀키를 운영 환경에 넣고 Android·iOS 개발 빌드에서 검증한다. `.env.example`은 템플릿이며 비밀 값은 소스 저장소에 커밋하지 않는다. EXPO_PUBLIC 변수는 공개 SDK 설정만 포함한다.
4. API 및 프록시에서 OAuth 콜백 쿼리와 Authorization 헤더를 로그에 남기지 않는다. Docker API 실행은 `--no-access-log`를 사용한다. 프록시 로그는 쿼리를 제외한 경로만 기록한다.

## Google·Apple·네이버·카카오

기존 네이티브 SDK로 받은 자격 증명을 서버가 검증한다. 계정 연결은 로그인 토큰을 교체하지 않으며 이메일이 같다는 이유로 계정을 병합하지 않는다. 다른 사용자에게 연결된 계정, 같은 서비스의 두 번째 계정, 마지막 로그인 수단 해제를 차단한다. 이전 중복 연결 데이터도 제공자 종류가 하나면 해제할 수 없다.

- Google: 앱 `EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID`, iOS 클라이언트 ID 및 콘솔의 Android 패키지·SHA 인증서를 설정한다. 서버 `GOOGLE_CLIENT_IDS`에 해당 audience를 넣는다.
- Apple: 기존 `APPLE_*` 승인 코드 교환·암호화·철회 설정을 모두 완료한다. iOS Sign in with Apple capability가 필요하다. 연결 해제/탈퇴 시 서버에서 권한을 철회한다.
- 네이버: 네이티브 SDK ID/secret, 앱 패키지와 URL scheme 등록 후 서버 `NAVER_LOGIN_ENABLED=1`. SDK가 요구하는 앱 배포용 설정이며 서버의 다른 API 비밀키를 재사용하지 않는다.
- 카카오: 앱 native key와 서버 숫자 `KAKAO_APP_ID`, 플랫폼 key hash/URL scheme을 일치시킨다. 설정 없이 토큰을 받아주는 이전 동작은 제거했다.
- 웹 체험은 실제 네이티브 인증을 실행하지 않는다. 정식 모바일 앱이 검증 대상이며 웹 OAuth 로그인은 이번 범위에 포함하지 않았다.

## Instagram 프로필 연결

공식 Instagram Login은 **비즈니스·크리에이터 계정**용이다. 일반 개인 계정용 Basic Display 대체 기능으로 표시하지 않는다. 앱 로그인 수단과 별개이며 자동 게시·피드 수집은 하지 않는다.

Meta 콘솔에서 Instagram Login 제품, `instagram_business_basic` 권한, 앱 검수 및 공개 배포 설정을 완료한다. 서버에 `INSTAGRAM_CLIENT_ID`, `INSTAGRAM_CLIENT_SECRET`, `INSTAGRAM_REDIRECT_URI=https://실제API/v1/social/instagram/callback`을 설정한다. 콘솔에도 동일한 HTTPS redirect URI를 등록한다. 사용자 데이터 삭제 정책·Meta 검수에 필요한 운영 URL도 준비한다.

인증 요청은 로그인 사용자에게 묶인 10분짜리 일회성 state를 사용한다. 승인 코드는 서버에서 교환하며 토큰은 보관하지 않고 확인된 계정 ID·사용자명만 저장한다. 만료·재사용·중도 연결 해제를 처리한다. 연결 해제는 앱 내 식별자를 지우며 Instagram의 앱 및 웹사이트에서 권한을 직접 철회하는 방법도 안내한다.

## 후원·구독 (RevenueCat + App Store / Google Play)

- 앱의 두 공개 SDK 키: `EXPO_PUBLIC_REVENUECAT_IOS_KEY`, `EXPO_PUBLIC_REVENUECAT_ANDROID_KEY`.
- 서버의 별도 API v1 키: `REVENUECAT_SECRET_KEY`. `PREMIUM_ENTITLEMENT=photospot_plus`.
- 각 스토어에 일회성 **소모성 후원** 상품과 자동 갱신 Plus 구독 상품을 만들고 RevenueCat에 가져온다. `tips` offering에는 후원, `plus`에는 구독을 연결한다. 후원 상품에 Plus entitlement를 연결하지 않는다.
- Plus entitlement에 구독만 연결한다. Plus는 배너/제휴 광고 숨김, 사진 필터, 최소 정합도 필터를 제공한다. 기존 점수의 가중치를 유료로 조작하지 않는다.
- 상품 가격·기간·이름은 스토어 조회 결과를 사용한다. 하드코딩 가격이나 가짜 구매 성공을 사용하지 않는다. 준비되지 않은 환경에서는 결제를 비활성화한다.
- SDK App User ID는 서버 인증된 PhotoSpot UUID로 지정한다. 구매·복원 후 서버가 RevenueCat에서 해당 계정의 만료일을 조회한다. 운영 서버는 sandbox 구독을 인정하지 않는다. 상태는 최대 15분 캐시하며 오래된 상태로 권한 판단 전 재조회한다. 결제 완료 후 일시적 서버 오류는 재결제 대신 상태 재확인을 안내한다.
- RevenueCat의 App Store Server Notifications / Google Play RTDN 연결과 구매 복원·계정 이전 정책을 운영자가 검토한다. 환불/취소 정보가 RevenueCat에 전달돼야 서버 재조회에도 반영된다.
- Android 결제 앱 전환을 위해 MainActivity launchMode를 `singleTop`으로 설정하는 Expo 플러그인을 추가했다. iOS IAP capability, 상품 심사, 테스트 계정은 별도 준비한다.
- 실제 가격으로 판매하기 전 Sandbox/TestFlight/Play 내부 테스트에서 성공, 취소, 보류 결제, 복원, 만료, 환불, 계정 전환, 탈퇴 안내를 검증한다. 앱 계정 삭제는 스토어 구독을 취소하지 않는다.
- 현재 웹 결제는 제공하지 않는다. 수입·수수료·환불 정산은 각 스토어와 RevenueCat 콘솔에서 확인한다.

## 배너·유료 장소 추천

이번 배너는 **직접 계약한 업체의 자체 광고**다. AdMob 등의 광고 네트워크 SDK나 광고 식별자 추적은 추가하지 않았다. 광고 등록 자체는 결제하지 않으며 업체 과금은 계약·정산 절차로 운영한다.

관리자 화면에서 실제 장소 상세 URL/UUID, 광고주, 문구, 위치(배너/우선 추천), 기간을 입력해 초안을 만들고 장소를 확인한 뒤 승인한다. 공개 활성 장소이면서 연결된 사진이 있어야 한다. 현재 날짜, 검색 반경, 공간 종류 조건을 모두 만족하는 승인 광고만 위치별 최대 1건 노출한다. 하루 단위로 순서를 순환한다. `광고`와 광고주를 표시하고 무료 추천 정합도에는 영향을 주지 않는다. Plus에는 광고를 숨긴다.

불러오기/클릭은 계정·날짜·광고별 중복 집계를 막는다. 이는 화면에 내려받은 광고 기록이며 실제 가시 노출 보증이나 사기 방지된 과금 지표가 아니다. 정산에 사용하지 않는다. 표시 이미지의 광고 활용 권리 및 광고 문구는 계약 시 확인한다.

## 피드백 → GPT → 개발자 승인

서버에 `OPENAI_API_KEY`, `FEEDBACK_MODEL`을 설정한다. 기본 모델은 `gpt-4o-mini`이며 Responses API의 strict JSON Schema를 사용한다. 외부 전송은 관리자 분석 버튼으로만 실행한다.

1. 이용자는 분류와 5~2000자 의견을 보낸다. AI 분석 동의는 기본 해제다. 일반 접수는 동의 없이 가능하다.
2. 관리자가 원문에서 이름·연락처·주소·계정 등 개인식별 정보를 직접 제거하고 검토본을 저장한다. 추가 정규식 마스킹은 보조 수단이며 완전 익명화를 보장하지 않는다.
3. 동의+검토 완료된 의견을 최대 20개 선택해 분석한다. 사용자 계정·프로필·생년월일·위치는 보내지 않는다. `store:false`로 요청하지만 OpenAI의 별도 보안상 보관 정책까지 없애는 설정은 아니다.
4. GPT가 유사 의견을 묶고 영향·긴급도·예상 노력·완료 기준을 제안한다. 피드백은 신뢰할 수 없는 데이터로 취급한다. 거부·미완성·형식 오류·없는 근거 ID·중복/누락 ID는 저장하지 않는다. 제보자 수는 서버가 직접 계산한다.
5. 점수는 `(영향×3 + 긴급도×2 + 고유 제보자 수[최대 5]) / 예상 노력`. 추정값은 개발자가 검토한다. 제안→승인→계획→완료의 순서를 강제하며 검토 메모·운영 기록을 남긴다. 코드 수정·자동 배포는 실행하지 않는다.

일일 분석 한도는 전체 관리자 합계 20회이며 실패한 요청도 포함한다. 이미 분석한 의견은 중복 과금되지 않게 차단한다. OpenAI 프로젝트의 별도 사용량 한도도 설정한다. 의견 삭제/탈퇴 시 해당 원문과 연결된 AI 개선안을 삭제한다. 이미 전송된 데이터의 제공자 보관은 개인정보 처리방침에서 안내한다.

관리자 계정은 `users.is_admin`을 운영자가 부여한다. 클라이언트 토큰에 쓴 역할을 신뢰하지 않고 서버 DB에서 조회한다. 스스로 권한을 올리는 API는 없다.

## 검증 기록 (2026-10-07)

- 전체 Python: 297 통과 / PostgreSQL 등 환경 미설정 33 건너뜀. 이후 OAuth 취소·필터·광고 테스트 추가 검증 결과는 RELEASE_STATUS 참고.
- 클라이언트 토큰/연결/구매 상태 테스트, 앱 타입 검사, 격리된 브라우저 체험 저장 테스트.
- Android·iOS Hermes 및 웹 번들 생성 성공. 이는 서명된 AAB/IPA 빌드나 실제 스토어 심사 완료를 의미하지 않는다.
- 실제 OAuth, Meta 검수, 결제 및 GPT 호출은 운영 키·스토어 설정 부재로 실행하지 않았다. PostgreSQL 017 마이그레이션은 이 PC에서 실제 DB 적용 검증을 하지 못했다.
- `tests/test_growth_database.py`의 영속성·동의·승인·구독 상태 통합 테스트 2개는 PostgreSQL을 제공하는 CI에서 실행하도록 추가했다. 로컬에서는 생략했다.
- npm의 호환 범위 내 보안 패치를 적용해 critical 1건을 제거했다. Expo 54 계열 전이 의존성의 high 24 / moderate 16 경고는 남아 있으며 메이저 업그레이드와 별도 회귀 검증이 필요하다. `npm audit fix --force`는 실행하지 않았다.

## 공식 문서

후속 배포 준비에서 PostCSS를 8.5.29로 고정하여 관련 경고를 제거했다. 최신 npm 검사 결과는 **high 23 / moderate 16 / critical 0**이다. [PostCSS 보안 권고](https://github.com/advisories/GHSA-fxqj-rqcc-2cmp)의 수정 기준을 따른다. [braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm), [node-forge](https://github.com/advisories/GHSA-86w9-cpqp-85rv)에는 확인 시점에 수정 버전이 없었다. 빌드 도구 경로를 포함한 경고이며, 실제 출시 전 SDK 업그레이드·영향 분석을 별도 완료해야 한다. 경고를 숨기는 무조건적인 major override나 Expo 하위 버전 강제 변경은 하지 않았다.

- [OpenAI Structured Outputs](https://developers.openai.com/api/docs/guides/structured-outputs?api-mode=responses)
- [Meta Instagram Login](https://www.postman.com/meta/instagram/folder/1z5vxzu/instagram-api-with-instagram-login)
- [RevenueCat Expo](https://www.revenuecat.com/docs/getting-started/installation/expo), [일회성 구매](https://www.revenuecat.com/docs/platform-resources/non-subscriptions), [API v1](https://www.revenuecat.com/docs/api-v1)
- [Apple App Review Guidelines](https://developer.apple.com/app-store/review/guidelines/), [Google Play 결제 정책](https://support.google.com/googleplay/android-developer/answer/10281818?hl=en)
