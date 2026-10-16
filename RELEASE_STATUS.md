# 포토스팟 출시 상태

기준: 2026-10-16. 웹 체험은 [운영 주소](https://photospot-nu.vercel.app/home)에 배포합니다. Android·iOS는 출시 후보이며 스토어 제출을 완료한 상태가 아닙니다.

검토·수정 범위는 [초기 37건](REVIEW_2026-10-12.md)과 [추가 16건](REVIEW_FOLLOWUP_2026-10-12.md)에 기록합니다. 테스트 수는 각 단계의 실행 결과이며 최종 커밋의 [CI 실행](https://github.com/LITAandD/photospot/actions/workflows/ci.yml)을 기준으로 확인하세요.

## 현재 동작

- 사진별 좋아요·취소를 공용 PostgreSQL에 저장하고, 좋아요 내림차순으로 대표사진을 선택합니다. 공개 웹은 서명된 브라우저 쿠키별, 로그인 앱은 계정별 1표이며 같은 요청의 재시도는 중복 집계하지 않습니다. 정합도 사진 지표는 선택된 대표사진의 분석값만 사용하고 미분석 항목은 미평가로 남깁니다. 조회 시 외부 사진을 내려받지 않으며 좋아요 자체는 정합도 점수에 더하지 않습니다. 저장소 구성·동점·분석 실패 처리: [웹 배포 안내](deploy/VERCEL.md).

- 기본 `catalog` 백엔드에서 웹·인증 API가 같은 장소·점수·사진을 사용합니다. PostgreSQL은 인증·동의·북마크·피드백·결제 상태를 보관합니다. `scenes`는 기존 사진 분석용 대체 백엔드입니다.
- 전체 정합도 점수를 우선 정렬하고 평가 범위와 거리 등을 동점 기준으로 사용합니다. 키는 실내/실외 추천 점수에 사용하지 않습니다. 개인 오행·촬영일 일진은 선택 시 반영합니다.
- 피드는 썸네일·장소명·정합도·운영시간·거리만 표시합니다. 상세에는 파이차트·지표 설명과 사진 위 포즈 스케치를 제공합니다. 검수된 사진은 실제 인물 비율을 적용하고 수동 크기 보정도 가능합니다.
- 포즈는 서 있기·움직임·앉기 각 4가지, 총 12가지이며 미리보기와 좌우 반전을 제공합니다. 앉거나 쪼그린 자세도 같은 체격과 바닥 위치를 기준으로 표시하고, 포즈를 바꿔도 인물 크기 보정과 배치 위치를 유지합니다.
- 재사용 권한을 확인한 사진만 공개합니다. 공식 브랜드 사진은 기본 제외하며 인스타그램은 검증된 공개 원본 링크를 사용합니다. 변경 금지 사진은 자르거나 스케치를 겹치지 않습니다.
- 코엑스는 2026-10-13 검수에서 연결 사진 98장 중 공간 사진 18장만 공개합니다. 인물·공연 66장, 공간과 무관한 사진 10장, 확인 보류 4장은 대표 사진·갤러리·사진 수 집계에서 제외합니다. 새 사진은 공간 검수 후 공개하며 원본 수집 기록은 보존합니다.
- 다른 장소도 사진별 검수에서 확인한 인물 클로즈업·단체 기념사진·인터뷰·공연 사진을 제외합니다. 동일한 Commons 원본이 다른 장소나 새 썸네일 URL로 연결되어도 제외하며, 배경의 방문객·조각상·전시 모형은 인물 사진으로 일괄 제외하지 않습니다. 검수 기록과 출처는 `pipeline/data/place_photo_subject_reviews.json`에 보관합니다. 이번 추가 검수에서 51개 장소 항목의 인물·공연 사진 605장(장소 연결 645건)을 제외하고 대표사진 6곳을 교체했습니다.
- 추가 검수 범위: 209개 장소의 사진 연결 6,875건의 제목·설명을 점검하고, 인물·행사 후보와 대표사진을 우선해 카탈로그 사진 1,436장과 편집 사진 7장을 직접 확인했습니다. 제외 대상 중 525장은 이미지 검수, 80장은 원본 제목·설명이 특정 공연자·인물 초상을 명시한 근거로 분류하며 검수 방법과 원문 설명을 구분해 보관합니다. 교체 후 현재 공개 대표사진을 다시 확인했습니다. 반복적인 이미지 서버 429 응답으로 추가 선택 후보 198장은 이미지 확인을 보류했으며, 전체 원본 사진의 육안 전수 검수는 아닙니다.
- 공식 날짜별 운영시간은 게시된 날짜에만 사용합니다. 현재 추천 대상 공식 지점 3곳은 10/12 확인, 10/18까지 갱신했습니다. 주간 갱신 workflow는 PR을 생성하며 운영 반영에는 병합이 필요합니다.
- 인스타그램 임베드를 제거하고 기존 연결 장소 16곳 모두를 재사용 허용 공간 사진으로 대체했습니다. 12곳에 CC·공공누리 1유형 사진 21장을 추가하여 총 25장을 직접 표시합니다. 원문 지점·라이선스·공간 구도 검수 기록은 `pipeline/data/naver_photos.json`, `kogl_photos.json`, `photo_framing_reviews.json`에 보관합니다. 사진이 없는 장소만 검증된 원본 링크를 안내합니다.

## 재현 검사

```sh
python -m pip install -r requirements-dev.txt -r requirements-quality.txt
python -m scripts.check_dependencies
python -m ruff check api pipeline saju scripts tests
python -m mypy
python -m pytest tests -q
npm --prefix client test
npm --prefix app run typecheck
npm --prefix app test
```

CI는 PostGIS 서비스에서 `scripts.migrate --seed`, 재실행, 상태 확인, 전체 Python 테스트, OpenAPI 일치, 사진-점수 무결성, 모든 플랫폼 export와 Playwright 웹 여정을 실행합니다. `security` 작업은 pip-audit와 npm audit 결과를 첨부합니다. Python은 발견 시, 클라이언트는 high/critical을 차단합니다. 앱은 critical을 항상 차단하고, 모든 등급의 새 권고·설치 버전·의존 경로 변화·검토 기한 만료도 차단합니다. 감사 실패나 불완전한 응답을 통과로 취급하지 않습니다.

## 2026-10-16 의존성 보안 검토 반영

Expo 55.0.31, React Native 0.83.10, React/renderer 19.2.0으로 공식 SDK 조합을 맞췄습니다. SDK 55의 타입 생성 경로와 설정 플러그인 해석 변경을 반영하고, Google 설정 플러그인의 직접 의존성을 명시했습니다. 동적 설정은 Expo가 넘긴 정적 설정을 병합하고, Android 밝은 테마에 필요한 `expo-system-ui`를 포함합니다. SDK 업데이트 단계에서는 단독 major override나 `npm audit fix --force`를 적용하지 않았습니다. 아래 후속 검토에서 실제 호출 API를 검사한 세 경로에만 범위를 한정한 override를 추가합니다. 기존 PostCSS override는 유지합니다.

2026-10-16 npm 감사는 SDK 54의 **high 23 / moderate 16**에서 SDK 55의 **high 22 / moderate 14**로 변했습니다. 이는 전파된 패키지 경고 수입니다. 원인 권고는 7건에서 5건으로 줄었고, Metro의 `image-size` 경로에 있던 GHSA-5p2g-fcmc-qvqq·GHSA-w3rx-r6r6-pgpr 2건이 제거됐습니다. 나머지는 해결 완료가 아닙니다.

남은 권고별 버전·경로·사용 범위·완화책은 [검토 예외 목록](security/app-audit-exceptions.json)에 기록합니다. 재검토 기한은 **2026-11-16**이며, 기한부터 CI가 실패합니다. 예외는 자동 갱신하지 않습니다. `braces`, `node-forge`, `sprintf-js`, `uuid`는 확인한 세 플랫폼 소스맵에 없고, `decode-uri-component`는 포함됩니다. Router의 직접 `query-string` 호출은 `stringify`이며 취약한 파싱 함수까지의 외부 입력 도달 경로는 확인하지 못했습니다. 이는 안전성 증명이 아닙니다.

`node scripts/check-app-audit.cjs`는 GHSA·영향 범위·정확한 설치 버전과 위치·모든 선행 의존 연결의 해시를 검사합니다. `node scripts/check-app-audit.cjs --maps app/dist`는 웹·Android·iOS 소스맵과 원문이 모두 존재하는지, 대상 패키지의 포함 플랫폼과 직접 import 코드 해시가 검토 기록과 같은지 검사합니다. 이 검사는 동적 호출 전체의 도달 가능성을 증명하지 않으며, 직접 import가 없는 간접 호출 변경도 수동 검토해야 합니다. 소스맵은 CI 검증에만 생성하며 운영 Vercel 빌드에는 포함하지 않습니다.

타입·앱 회귀 검사, SDK 버전 검사, 세 플랫폼 export와 Android 설정 생성 검사를 로컬에서 수행했습니다. 최종 Expo Doctor는 **19/20**입니다. Google·카카오의 기존 설정 플러그인이 `@expo/config-plugins`를 직접 import하므로 SDK 55 버전을 개발 의존성으로 명시했고, 이 직접 설치 경고 1건이 남습니다. Doctor가 설명하는 플러그인 호환성 예외이며 해당 의존성을 제거하면 테스트용 로그인 설정의 prebuild가 실제로 실패합니다. 검사를 끄거나 성공으로 바꿔 표시하지 않습니다. 앱 자체 플러그인은 `expo/config-plugins`를 사용합니다.

CI는 테스트용 공개 Google·카카오 ID로 Android/iOS를 `prebuild --no-install`하고 콜백 스킴·Apple entitlement·`singleTop` 복귀·권한 설명을 확인합니다. 이것은 Gradle/Xcode 서명 빌드나 실제 OAuth·구매 검증을 대신하지 않습니다. Expo 공식 [SDK 55 변경사항](https://expo.dev/changelog/sdk-55)과 [단계별 업그레이드 절차](https://docs.expo.dev/workflow/upgrading-expo-sdk-walkthrough/)를 기준으로 검증했습니다.

### 잔여 5건 후속 수정

추가 검토에서 3건을 제거해 원인 권고는 **5 → 2건**, npm 전파 경고는 **high 22 / moderate 14 → high 22 / moderate 0**이 됐습니다. SDK와 앱 기능은 유지하며 다음 의존 경로만 교체합니다.

- `decode-uri-component`: [공식 수정 버전 0.5.0](https://github.com/advisories/GHSA-vcc3-ghjq-m6fr)을 npm alias로 설치합니다. `query-string@7.1.3`의 CommonJS 호출에는 `app/compat/decode-uri-component`의 작은 어댑터로 같은 upstream 함수를 전달합니다. 디코딩 알고리즘을 복사하거나 직접 수정하지 않습니다. 한글·이모지·공백·중복 쿼리·빈 값·배열과 잘못된 인코딩 입력의 종료 시간을 검사합니다.
- `uuid`: `xcode@3.0.1` 경로에만 [공식 수정 버전 11.1.1](https://github.com/advisories/GHSA-w5hq-g745-h8pq)을 지정합니다. 실제 Xcode의 `generateUuid()` 호출과 UUID v3/v5/v6의 출력 버퍼 경계 거부를 검사합니다. Android/iOS 설정 생성도 CI에서 다시 검증합니다.
- `sprintf-js`: [공식 수정 버전은 없으므로](https://github.com/advisories/GHSA-hp3w-g68c-fv3c) `@istanbuljs/load-nyc-config@1.1.0`의 `js-yaml`을 4.3.2로 한정해 교체합니다. 실제 상위 도구가 쓰는 `load()`와 YAML 설정 상속·배열·불리언·숫자·잘못된 문서 처리를 검사합니다. `argparse` 2를 통해 취약한 `sprintf-js` 자체가 설치 트리에서 제거됩니다.

어댑터의 동기 ESM 로딩을 위해 Node **22.13.0 이상**을 명시합니다. CI는 Node 22, Vercel은 Node 24를 사용하며 EAS 프로필은 Node 22.23.3으로 고정합니다. 패키지 버전·출처·무결성은 잠금 파일로 고정하고, 소스맵 검사에 어댑터가 연결하는 upstream 디코더를 포함합니다.

남은 [braces](https://github.com/advisories/GHSA-vfj7-8cjw-p6xm)와 [node-forge](https://github.com/advisories/GHSA-86w9-cpqp-85rv)는 2026-10-16 공식 npm/권고 기준으로 수정 버전이 없습니다. 빌드 패턴 처리와 인증서 도구에 사용되며 현재 세 플랫폼 실행 번들에는 없습니다. 검증되지 않은 AST·암호 검증 패치를 자체 작성해 해결로 처리하지 않습니다. 당시 두 예외의 경로 해시·완화책·2026-11-16 만료를 유지했으며, 아래 대체 작업에서 두 예외를 제거했습니다. 네이티브 서명 빌드와 실제 로그인·결제는 여전히 별도 검증 범위입니다.

### 나머지 2건: 빌드 도구의 라이브러리 대체

앞선 단계에서 보류했던 `braces`·`node-forge` 원본 패키지를 제거했습니다. `security/app-audit-exceptions.json`의 예외는 이제 빈 목록이며 알려진 npm 권고는 0건입니다. SDK 55 조합은 유지합니다.

- Metro/Jest의 `micromatch` 호출을 Picomatch 4.0.7 기반 로컬 어댑터로 연결합니다. 기존 목록 선택·부정 패턴 순서는 MIT 라이선스와 함께 보존하고 `braces` AST/확장 코드는 포함하지 않습니다.
- Expo CLI의 `node-forge` 이름은 iOS 인증서 CN/O/OU 조회만 제공하는 `@photospot/expo-certificate-reader` 로컬 패키지로 해석됩니다. npm 패키지명만 바꾼 포크가 아니라 Node `X509Certificate`를 사용하는 별도 구현입니다.
- `@expo/code-signing-certificates` 호출은 `@photospot/expo-code-signing`으로 연결합니다. Node/OpenSSL이 RSA 키 생성·서명·검증을 처리하고, Peculiar의 공식 ASN.1 스키마가 동기 CSR을 인코딩합니다. Expo의 호출 방식·PEM 키와 인증서 파일·manifest 서명 형식은 유지합니다.
- 호환 계층은 전체 원본 API를 흉내 내지 않습니다. 현재 사용 중인 7개 소비 파일의 버전·해시와 새 import 유무를 `security/compat-consumers.json`으로 고정하며, Expo/Metro/Jest 업데이트 시 재검토 없이 통과하지 않습니다. 로컬 어댑터가 실행 번들에 섞여도 배포 검사가 실패합니다.

새 설치 후 앱 타입·회귀 검사, 모든 플랫폼 export, 네이티브 설정 생성, 보안 감사와 웹 사용 흐름을 검증합니다. 추가 검사는 실제 Expo CLI의 manifest 서명·CSR 생성·iOS 인증서 정보 추출, 만료/미래 인증서, 용도 누락, 키 불일치, 변조와 잘못된 RSA DigestAlgorithm 거부를 포함합니다. iOS 키체인 명령은 테스트에서 대체하며 실제 기기 서명·스토어 배포·OAuth/결제는 별도 출시 검증 범위입니다.

추가 검토의 변경·검증 범위는 [16건 반영 기록](REVIEW_FOLLOWUP_2026-10-12.md)에 정리했습니다. 영업시간 갱신은 빈 카탈로그·25% 초과 퇴역을 차단하고, 부분 성공은 실패 지점의 기존 날짜를 보존한 채 PR로 올립니다.

`artifacts/`는 테스트·수집 시 생성되는 로컬 출력 폴더이며 Git에 포함되지 않습니다. 공개 검증 자료는 CI 실행 페이지의 `ui-screenshots`, `security-reports`, 데이터 갱신 작업의 `data-refresh-reports`를 확인하세요. 배포 데이터 출처·해시·행 수는 추적되는 [카탈로그 manifest](catalog/places.manifest.json)에 있습니다.

## 운영 전 남은 범위

실제 OAuth/Meta 승인·RevenueCat 결제·Apple 탈퇴를 운영 계정과 실기기에서 검증해야 합니다. CI의 테스트 제공자와 가짜 HTTP 검사는 이를 대신하지 않습니다. 여러 서버 인스턴스에 걸친 요청 제한은 별도 공용 저장소 또는 WAF가 필요합니다. 공개 이미지 이용 허락, 저장소 배포 라이선스, 다국어 지원과 스토어 설정은 각각의 범위로 관리합니다.
