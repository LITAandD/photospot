# 포토스팟 1.0 출시 후보 점검

기준일: 2026-10-07. 이 문서는 코드 검증 결과와 아직 실제 계정·서버에서 확인해야 할 사항을 구분합니다. 스토어 제출이나 운영 배포는 수행하지 않았습니다.

## 계정이 없는 현재 단계에서 완료한 준비

- 앱의 공개 API·정책·약관·외부 탈퇴 URL, EAS 프로젝트, 로그인과 결제 설정을 한 번에 검사합니다. 운영 EAS 설정 평가에서도 같은 검사를 실행합니다. 개발 토큰, 로컬/사설 IP, 예시 도메인, URL 내 비밀번호, 테스트 결제 키는 거부합니다.
- 서버 검사 `python -m scripts.check_release --env-file .env --growth`는 네트워크 호출 없이 누락 항목을 표시합니다. 서버 준비 후 `--database`를 추가하면 읽기 전용으로 PostGIS·미적용 마이그레이션·개발 시드 기록을 확인합니다.
- 마이그레이션 조회 `python -m scripts.migrate --status`는 테이블을 만들지 않습니다. 미적용 파일이 있으면 종료 코드 1을 반환합니다. 실제 적용은 배포 간 잠금을 사용하고 파일별로 커밋합니다. 실패한 파일은 롤백하고 앞서 완료한 파일부터 다시 실행하지 않습니다. 운영 `--seed`는 차단합니다.
- Git/Docker 배포 대상에서 환경 파일과 Apple 키·서명 파일을 제외합니다. 이미 외부로 보낸 비밀키를 폐기하는 기능은 아니므로 기존 유출이 있다면 별도 교체가 필요합니다.
- `release-candidate` EAS 프로필은 운영 검사를 적용하면서 내부 설치용 빌드를 생성합니다. 현재 계정·설정이 없어 실제 빌드는 실행하지 않았습니다.

계정 준비 순서는 다음과 같습니다. 신원 확인·유료 계약·스토어 약관 동의는 운영자가 직접 진행해야 하며, 발급 후 기술 설정과 검증은 이 프로젝트에서 이어갈 수 있습니다.

| 순서 | 운영자가 준비할 항목 | 이어서 실행할 작업 |
|---|---|---|
| 1 | 운영자명·문의 연락처, 도메인·서버·PostGIS 호스팅 | HTTPS, 접근 제한, 저장소·백업/복구, 정책·외부 삭제 페이지 구성 |
| 2 | Expo 및 Apple/Google 개발자 계정, 앱 식별자 소유 확인 | EAS 연결, 서명, Google/Apple 로그인 설정 및 실기기 로그인·탈퇴 |
| 3 | 네이버·카카오·Meta 개발자 앱 승인 | 콜백·서명 등록, Instagram 프로 계정 연결·취소·해제 검증 |
| 4 | RevenueCat·스토어 상품, OpenAI API 프로젝트 | 후원/구독 sandbox 검증, 개인정보 제거 후 GPT 분석 확인 |
| 5 | 실제 iPhone·Android 테스트 기기와 심사 정보 | 서명 빌드, TestFlight/내부 테스트, 남은 보안 경고·사진 권리 검토 후 제출 |

비밀키는 채팅에 붙이지 않고 환경변수나 비밀 저장소에 넣습니다. 공개 SDK 키와 서버 전용 비밀키를 구분하는 항목별 안내는 [GROWTH_SETUP.md](GROWTH_SETUP.md)에 있습니다.

## 수정한 주요 문제

- Windows 클라이언트 빌드의 `cp` 오류, 오래된 OpenAPI 타입, 새 라우트 타입 생성 누락.
- 온보딩 건너뛰기 시 프로필 미저장, 출생연도·키·생년월일·시간 검증, 음력 2월 30일과 윤달 입력.
- 사진 후기에서 `scene_id`를 `spot_id`로 보내던 오류, 웹 업로드의 Blob 변환, 남의 사진 연결 차단.
- 위치 조회 실패·권한 거절·국외 좌표에 대한 안내. 지역·반경·시간대·방문일 선택과 빈 결과 처리.
- 정보가 없는 계정도 근거가 확인된 주변 장소를 볼 수 있도록 기본 추천 수정. 개인 점수가 없는 경우 0점을 궁합으로 표시하지 않음.
- 실제 사진 표시와 출처·원본 비율 유지, 계정별 북마크, 프로필 수정·로그아웃·탈퇴, 사주·사진 동의 철회.
- 토큰의 필수 만료 정보 검증, DB 기반 관리자 권한 확인, 동시 갱신 처리와 일시적 네트워크 오류 시 세션 보존.
- 사용자 업로드를 공개하지 않는 `/media` 경로, 저장 경로 이탈 차단, 삭제 파일의 재시도 작업과 사진 근거 재집계.
- 잘못된 기본 운영 설정 차단, Android/iOS EAS 프로필, 아이콘, 자동 CI 검사.

## 검증 범위

최종 검사 수치와 실행 결과는 루트 `RELEASE_STATUS.md`를 확인합니다.

- Python 단위·HTTP 회귀 테스트, TypeScript 클라이언트 테스트, 앱 타입 검사를 실행했습니다.
- Android/iOS Hermes 바이트코드와 웹 번들을 생성했습니다. 이것은 서명된 AAB/IPA 빌드 성공과 다릅니다.
- Chrome 390×844 환경에서 초기 사주 입력 제거, 실제 프로필 결과 카드, 촬영일의 선택 오행·일진, 생년월일 8자리 자동 표시, 12지시 선택, 실제 장소 출처·저장·수정·탈퇴를 검증했습니다. 로컬 앱은 실제 입력을 Python 계산기로 처리하고 OpenStreetMap 장소 SQLite DB를 조회합니다. 장소 사진 분석에 따른 추천 품질이나 소셜 로그인은 이 검사로 검증하지 않습니다.
- 이 PC에는 Docker/PostgreSQL/PostGIS가 없어 DB 통합 검사는 실행되지 않았습니다. `.github/workflows/ci.yml`은 빈 PostGIS DB 마이그레이션·통합 검사와 앱 검사를 수행하도록 구성했습니다. GitHub에서 실제 실행됐다고 간주하면 안 됩니다.

## 운영 연결 전 반드시 준비할 것

1. **API와 DB**: HTTPS API 주소, PostgreSQL/PostGIS, 영구 저장소·백업, 실제 장소 데이터와 검수된 장면. 샘플 데이터는 운영 추천에 쓰지 않습니다.
2. **소셜 로그인**: Google·Apple 및 사용할 Naver/Kakao 앱 등록, Android 서명 해시·iOS URL scheme·서버 audience 설정. Apple 로그인은 실제 iOS 기기에서 확인해야 합니다. 토큰·키를 채팅이나 소스에 붙여넣지 않고 로컬 환경 변수/EAS 환경에 설정합니다.
3. **운영자 정책**: 실제 운영자·연락처·처리 목적·위탁/국외 이전·보유 기간 등을 담은 개인정보 처리방침, 이용약관, 앱 밖에서 삭제를 요청할 수 있는 HTTPS 페이지. 앱의 안내 화면은 완성된 법률 정책 문서를 대신하지 않습니다.
4. **스토어**: Apple Developer/Google Play 계정, Expo 프로젝트 ID, 소유한 고유 bundle/package ID, 서명, 연령 등급·개인정보/Data Safety 응답, 심사 계정, 소개와 실제 기기 스크린샷.
5. **실기기 검수**: Android/iOS에서 로그인·토큰 갱신·권한 거절·저장·업로드·탈퇴를 검증하고 최소 한 번 TestFlight/내부 테스트를 진행합니다.
6. **운영 제한**: 게이트웨이에서 로그인·업로드·일반 API에 속도/용량 제한을 적용하고, 작업 큐의 오래된 `running` 작업과 실패 작업을 모니터링합니다. 자동 복구가 없는 장시간 중단 작업은 확인 후 재처리해야 합니다.

## 서버 실행

루트 `.env.example`을 `.env`로 복사하고 값을 설정합니다. 기존 `.env`는 이번 작업에서 덮어쓰지 않았습니다.

```sh
docker compose up --build -d
```

마이그레이션은 `schema.sql`부터 `017_product_growth.sql`까지 순서대로 적용됩니다. 015는 공개 장소 저장 목록, 016은 암호화한 Apple 갱신 토큰 보관, 017은 SNS 연결·구독·광고·피드백 운영용입니다. 신규 기능 설정은 [GROWTH_SETUP.md](GROWTH_SETUP.md)를 따릅니다. 개발용 예시 데이터가 필요할 때만 아래를 실행합니다.

```sh
docker compose run --rm migrate python -m scripts.migrate --seed
```

운영에서는 `APP_ENV=production`, 충분히 긴 무작위 `JWT_SECRET`, `DEV_LOGIN=0`, 명시적인 HTTPS `CORS_ORIGINS`를 사용합니다. 기본 DB 암호는 개발 전용입니다. 운영 DB의 사용자·암호와 `DATABASE_URL`을 별도로 설정하세요. HTTPS 프록시 뒤에서는 실제 프록시 주소만 `FORWARDED_ALLOW_IPS`로 신뢰합니다.

`MEDIA_BASE_URL=/media`이면 요청 API 주소의 공개 사진 경로를 사용합니다. 저장소 전체를 정적 공개하거나 사용자 업로드를 CDN 공개 버킷에 넣지 마세요. 외부 CDN을 쓰려면 공개 출처의 사진만 게시하고 해당 URL을 지정해야 합니다.

```sh
python -m scripts.migrate --status
python -m pytest tests -q
python -m pipeline.run integrity
```

실제 데이터 수집은 `pipeline/BULK_IMPORT.md`, `pipeline/CAFE_SOURCES.md`를 따릅니다. 외부 API 키와 이용 조건을 확인하고, 사진 근거/수동 검수 조건을 통과한 장소가 각 서비스 지역에 충분한지 점검합니다.

## 앱 실행과 배포

Node.js 22 이상 권장. 저장소 최상위에 `client/`와 `app/`가 함께 포함되어야 합니다. 현재 폴더는 Git 저장소가 아니므로 EAS에 올리기 전 이 루트를 저장소로 준비해야 합니다. `app/`만 분리해 업로드하면 `file:../client` 의존성을 찾을 수 없습니다.

```sh
npm --prefix client ci
npm --prefix client run build
npm --prefix app ci
npm --prefix app run typecheck
npm --prefix app run export -- --max-workers 2
```

`app/.env.example`의 설정을 준비합니다. 휴대폰에서 `localhost`는 PC가 아니므로 개발 API 주소를 PC의 LAN IP로 바꿉니다. 운영은 반드시 HTTPS 주소를 사용합니다.

```sh
cd app
npm run check:release
npx eas-cli build --profile preview --platform all
npx eas-cli build --profile release-candidate --platform all
npx eas-cli build --profile production --platform all
```

EAS의 `eas-build-post-install`이 형제 디렉터리의 클라이언트를 빌드합니다. `EAS_PROJECT_ID`와 공개 앱 설정은 EAS 환경에도 등록해야 합니다. 프리뷰 빌드를 실제 기기에 설치한 뒤 운영 빌드로 진행합니다. `APP_VARIANT=production` 빌드에서 데모 로그인·개발 서버 주소·미설정 로그인 제공자는 거부됩니다. `npm run check:release`는 현재 빠진 설정을 확인하는 검사이며 실제 자격 증명 유효성은 확인하지 않습니다.

2026-10-06에 확인한 공식 안내를 기준으로 iOS 제출은 iOS 26 SDK 이상이 필요합니다. EAS production 프로필에 SDK 54 호환 Xcode 26.0 이미지를 지정했습니다. [Apple SDK 요구사항](https://developer.apple.com/news/?id=ueeok6yw), [Expo 빌드 이미지](https://docs.expo.dev/build-reference/infrastructure/).

Google Play의 계정 생성 앱은 앱 내 삭제 기능과 별도로 외부 삭제 요청 링크가 필요합니다. [Google Play 계정 삭제 안내](https://support.google.com/googleplay/android-developer/answer/13327111?hl=en).

## 컨셉 구현 범위

기본 추천 백엔드는 `RECOMMENDATION_BACKEND=catalog`입니다. 웹 미리보기와 인증 API가 같은 공개 장소·사진·오행·영업시간과 사진 특징 계산기를 사용합니다. 계정·프로필·저장 목록은 PostgreSQL에 유지합니다. 기존 장면 분석 API는 `RECOMMENDATION_BACKEND=scenes`로 선택합니다.

공개 장소를 갱신한 후 `python -m pipeline.cafe_photos`, `python -m pipeline.catalog_visuals --limit 10000`, `python -m scripts.export_catalog`을 순서대로 실행합니다. Docker는 `catalog/places.sqlite3`를 포함하고 `PLACE_CATALOG_DB`로 읽습니다. 사용자 정보·업로드·인증 토큰은 이 스냅샷에 포함되지 않습니다. 외부 HTTP 호출은 수집 명령에서만 수행합니다.

Apple 로그인은 앱이 받은 `authorizationCode`를 서버로 전달합니다. 서버가 같은 사용자·앱·nonce인지 검증한 후 갱신 토큰을 Fernet으로 암호화합니다. `APPLE_CLIENT_ID`, `APPLE_TEAM_ID`, `APPLE_KEY_ID`, `APPLE_PRIVATE_KEY_PATH`, `APPLE_TOKEN_ENCRYPTION_KEY`를 서버 비밀 저장소에 설정해야 합니다. `.p8` 파일은 해당 경로에 읽기 전용으로 마운트하세요. 앱 번들·소스에 키를 넣지 마세요. 암호화 키를 잃으면 기존 토큰을 복호화할 수 없으므로 비밀 저장소에 백업하고, 교체 시 기존 토큰을 재암호화해야 합니다.

탈퇴·Apple 연결 해제는 Apple `/auth/revoke` 성공 후 로컬 개인정보를 삭제합니다. 실패하면 계정과 로그인 세션을 유지합니다. 기존 토큰이 없는 계정은 iOS 재인증으로 복구하며, 새 로그인 계정은 서버에 보관된 토큰으로 어느 플랫폼에서도 삭제할 수 있습니다. 실제 Apple 발급·철회와 PostGIS 마이그레이션은 자격 증명이 준비된 환경에서 별도 확인해야 합니다.

아래는 별도의 운영 API에 구현된 사진 근거 기반 추천 규칙이며 실제 분석 자료를 연결한 뒤 검증해야 합니다.

퍼스널컬러·체형·키는 장면의 색·조명·형태·크기와 매칭됩니다. 성별은 키 구간 분류에 사용하고 MBTI E/I·S/N·T/F는 보조 점수입니다. 사주는 별도 추가 추천 탭의 `use_saju=true` 요청에만 반영합니다. 비율이 가장 낮은 오행(동률 포함)이 확인되는 장면을 선택하고, 보완 오행 가중치 8과 한국 날짜 기준 일진의 천간 오행 가중치 4를 사용합니다. 동률 오행이 여럿이어도 가중치를 중복 합산하지 않습니다. 비율이 모두 같으면 오행 필터 없이 일진만 추가합니다. 실용 적합성 기준은 그대로 유지합니다. 실제 API에 적용하기 전에 `014_place_group_filter.sql`까지 실행하고 DB 통합 검사를 통과해야 합니다. 출생연도와 MBTI J/P는 현재 장소 순위에 직접 반영하지 않습니다. 추천은 취향 탐색 규칙이며 검증된 성격 진단·운세·사진 결과 보장이 아닙니다.

웹은 개발/데모 검증용이며 정식 웹 소셜 로그인은 구현하지 않았습니다. 목표 출시 대상은 Android와 iOS입니다.
