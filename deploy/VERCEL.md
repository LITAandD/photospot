# Vercel 웹 체험 배포

저장소 루트의 `vercel.json`과 `pyproject.toml`로 웹 체험 버전을 배포합니다.
정식 회원 API·PostGIS·작업 처리기 배포와는 별도입니다.

## 구성

- Expo 웹 번들을 `app/dist`에 생성하고 Vercel CDN에서 제공합니다.
- FastAPI 진입점은 `deploy.vercel.index:app`입니다. `/preview/*`, `/health`, `/robots.txt`, `/sitemap.xml`을 처리합니다.
- 브라우저는 같은 도메인의 `/preview/*`를 호출합니다. 사진 좋아요를 사용하려면 아래 PostgreSQL·쿠키 서명키를 설정합니다.
- 프로필·오행 비율·저장 목록은 각 브라우저의 localStorage에 남습니다. 실제 회원가입·소셜 로그인·업로드·결제·GPT 분석은 제공하지 않습니다.
- 서버에는 공개 장소 스냅샷 `catalog/places.sqlite3`만 포함합니다. 읽기 전용 배포 파일을 수정하지 않도록 프로세스별 임시 디렉터리에 복사하여 조회합니다. 개인 계산 입력은 저장하지 않습니다.
- 클라이언트 경로를 직접 열거나 새로고침해도 `index.html`로 연결됩니다.
- 함수 리전은 `vercel.json`의 `"regions": ["icn1"]`(서울)입니다. Hobby 플랜은 리전 하나만 허용하며, 대시보드 Function Region 설정보다 이 파일이 우선합니다.

## GitHub에서 가져오기

1. Vercel에서 `LITAandD/photospot` 저장소를 가져옵니다.
2. Root Directory는 저장소 루트(`.`), Framework Preset은 FastAPI입니다.
3. Build Command는 `node scripts/build-web-preview.cjs`이며 `vercel.json`에 설정되어 있습니다. Output Directory와 Install Command는 기본값으로 둡니다.
4. 아래 환경변수만 서버(Production)에 설정합니다. 로컬 `.env`, 서버 JWT 키, 소셜 로그인 키를 업로드하지 않습니다.
5. 배포 완료 후 `/health`, 첫 화면, 체험 로그인, 추천, 사주 계산, 장소 상세의 직접 접속을 확인합니다.

`pyproject.toml`은 웹 체험에 필요한 Python 패키지만 지정합니다. 전체 API와 작업 처리기는 기존 `requirements.txt`를 계속 사용합니다.
`scripts/build-web-preview.cjs`는 클라이언트와 앱 의존성을 설치하고, 로컬 `.env`를 읽지 않은 상태에서 체험용 웹 번들을 만듭니다.

### 운영 환경변수

| 변수 | 운영값 | 설명 |
| --- | --- | --- |
| `PHOTO_LIKES_DATABASE_URL` | Neon 연결 문자열 | 좋아요·사진 분석·익명 이벤트 저장소. 비어 있으면 좋아요 버튼이 비활성화되고 이벤트는 버려집니다 |
| `PHOTO_LIKES_COOKIE_SECRET` | 32바이트 이상 무작위 | 익명 투표 쿠키 서명키 |
| `PHOTO_LIKES_ORIGINS` | `https://photospot.litaandd.com` | 좋아요 쓰기를 허용할 Origin. 프록시가 전달한 스킴에 의존하지 않도록 운영 도메인을 명시합니다 (`vercel env add PHOTO_LIKES_ORIGINS production`) |
| `PHOTO_LIKES_MIN_VOTES` / `PHOTO_LIKES_MIN_MARGIN` | 기본 `5` / `2` | 익명 표가 대표사진·정합도 근거를 바꾸는 최소 표 수와 큐레이션 대표사진 대비 여유분 |
| `PHOTO_LIKES_NEW_VOTERS_PER_DAY` / `PHOTO_LIKES_PER_DAY` | 기본 `30` / `200` | IP당 하루 새 투표 쿠키 발급 수·익명 좋아요 수 (인스턴스별) |
| `SENTRY_DSN` | 프로젝트 DSN | 설정했을 때만 Sentry가 켜집니다. 요청 본문·쿠키·IP·쿼리스트링(좌표)은 전송하지 않습니다 (`send_default_pii=False`, `max_request_body_size='never'`, `before_send`로 query_string 제거) |
| `PUBLIC_BASE_URL` | `https://photospot.litaandd.com` | `robots.txt`·`sitemap.xml`의 절대 주소 (기본값과 같으면 생략) |

`VERCEL=1`은 플랫폼이 설정하며, 이때 `x-forwarded-proto`·`x-real-ip`를 신뢰합니다. 다른 호스팅에서는 `FORWARDED_ALLOW_IPS`에 프록시 IP를 적어야 전달 헤더를 사용하고, 그 외 피어가 보낸 헤더는 무시합니다.

GitHub Actions의 `DATA_REFRESH_TOKEN` secret과 장애 대응 절차는 [OPERATIONS.md](OPERATIONS.md) 1절·4절.

## 로컬 검증

### 사진 좋아요 저장소

Neon 등 PostgreSQL에 `PHOTO_LIKES_DATABASE_URL`을 연결하고 `python -m api.photo_likes`를 한 번 실행합니다. 이 명령은 좋아요·사진별 분석·익명 이벤트 테이블만 생성하며 개인 프로필·생년월일을 저장하지 않습니다. `PHOTO_LIKES_COOKIE_SECRET`은 32바이트 이상 무작위 서버 비밀로 설정합니다. 둘 다 `EXPO_PUBLIC_` 변수로 노출하지 않습니다. 저장소 미설정 시 좋아요 버튼은 비활성화됩니다.

현재 운영은 Vercel Marketplace Neon Free 플랜(`photospot-photo-likes`, Singapore)에 연결합니다. 미리보기 배포·테스트에는 운영 DB를 연결하지 않습니다. API 통합 테스트는 PostgreSQL의 임의 테스트 스키마를 만들고 완료 후 제거합니다.

#### Neon 리전·풀러

- 함수가 서울(`icn1`)에서 실행되므로 Neon 프로젝트도 가장 가까운 리전(AWS Asia Pacific Singapore `ap-southeast-1`; 선택 가능해지면 서울)에 두고, 리전이 다르면 추천 요청마다 왕복 지연이 더해집니다. 리전 변경은 새 프로젝트를 만들어 `python -m api.photo_likes`로 테이블을 만든 뒤 `pg_dump`/`pg_restore`로 옮깁니다.
- 연결 문자열은 **pooled**(`-pooler` 호스트, PgBouncer transaction 모드)를 사용합니다. 인스턴스마다 최대 3개의 연결을 유지하므로 스케일아웃 시 직접 연결 한도를 넘지 않게 합니다. transaction 풀링은 세션 설정을 지원하지 않아 코드는 `SET LOCAL statement_timeout`만 사용하고, 조회는 한 번의 다중 문장 쿼리(표 합계 + 대표사진 근거)로 왕복 1회에 끝냅니다.
- Free 플랜의 자동 중지(autosuspend)는 첫 요청에서 수 초의 깨우기 지연을 만듭니다. 트래픽이 꾸준하면 Launch 플랜에서 중지 시간을 늘리거나 끄고, 컴퓨트 시간·연결 한도를 모니터링합니다.

#### 장애 시 동작

- 조회(추천·장소 상세·저장 목록)는 좋아요 저장소가 2초 안에 응답하지 않으면 `likes_enabled=false`로 계속 응답하고, 20초 동안 저장소를 건너뜁니다. 추천 화면은 좋아요 없이 정상 동작하며 실패는 분당 1회만 로그에 남습니다.
- 좋아요 쓰기만 `503 좋아요 저장소에 연결하지 못했어요`를 돌려줍니다. 알려진 장애 중에는 즉시 응답합니다.
- 로그인 계정 삭제는 저장소 장애 중에도 완료됩니다. 이때 남은 표의 식별 해시(계정 삭제 후 누구와도 연결되지 않음)를 ERROR 로그에 남기므로 복구 후 `python -m api.photo_likes revoke <voter_hash>`로 삭제를 마무리합니다. 정상 상태에서는 요청 안에서 표와 삭제 표식을 함께 처리합니다.
- `/health`는 `{ok, mode, catalog_version, likes:{configured, reachable}}`를 돌려줍니다. `ok`는 장소 카탈로그 적재 여부, `likes.reachable`은 1초 `SELECT 1` 결과이며 연결 문자열은 포함하지 않습니다. 저장소 장애에도 200을 유지하므로 모니터는 `likes.reachable`을 함께 확인합니다.

브라우저의 서명된 HttpOnly/SameSite 쿠키마다 사진당 1표를 집계하며 다시 누르면 취소합니다. 로그인 앱은 검증된 계정별로 집계합니다. 쿠키 삭제·다른 기기는 다른 방문자로 간주하므로 실명 사용자 수를 뜻하지 않습니다. 모든 사진에 좋아요 수를 표시하지만, 대표사진과 정합도 근거는 `PHOTO_LIKES_MIN_VOTES`표 이상이면서 큐레이션 대표사진보다 `PHOTO_LIKES_MIN_MARGIN`표 이상 많은 사진만 교체합니다. 동점이면 기존 근경·출처 우선순위를 유지합니다. 인물·공연 사진과 재사용 미허용 사진 필터는 투표보다 먼저 적용합니다. IP당 하루 새 투표 쿠키와 좋아요 수에는 인스턴스별 상한이 있습니다.

대표사진만 사진 정합도 근거가 됩니다. 좋아요 응답을 보낸 뒤 백그라운드에서 새 사진의 색조·명도·채도를 분석해 별도 DB에 보관하므로 하트는 외부 사진 호스트를 기다리지 않습니다. 형태는 해당 사진의 검토 근거가 있을 때만 평가하고, 기존의 다른 사진에서 태그를 빌리지 않습니다. 다운로드·분석 실패 시 좋아요는 보존하고 해당 사진 항목은 미평가로 표시하며 다음 좋아요 요청에서 재시도합니다. 좋아요 수 자체는 정합도 점수에 더하지 않습니다. 조회 요청에서는 외부 사진을 다운로드하지 않습니다.

개발 서버(8081/8001)를 함께 사용할 때 `PHOTO_LIKES_ORIGINS=http://localhost:8081,http://127.0.0.1:8081`을 설정합니다. 전체 API 배포도 같은 좋아요 DB 환경변수와 독립 초기화 명령을 사용합니다.

```sh
node scripts/build-web-preview.cjs
python -m pytest tests/test_vercel_preview.py tests/test_personal_preview.py tests/test_likes_resilience.py -q
python -m uvicorn deploy.vercel.index:app --host 127.0.0.1 --port 8082
```

마지막 명령은 실제 배포용 웹 번들과 계산 API를 같은 주소에서 제공합니다.
기존 `npm --prefix app run demo` 방식은 개발용 8081/8001 서버를 계속 사용합니다.

### 캐시·압축·보안 헤더

- `Cache-Control: no-store`는 `/preview/*`, `/v1/*`, `/health`, HTML 응답에만 붙습니다. 해시가 붙은 `/_expo/static/*`·`/assets/*`는 `public, max-age=31536000, immutable`로 CDN(`vercel.json` headers)과 로컬 FastAPI(`api.observability.ResponseHeaders`) 모두에서 1년간 캐시됩니다.
- GZip은 가장 안쪽 미들웨어라 1,000바이트 미만 응답(`/health` 등)은 압축하지 않고, 회원 API의 `/v1/auth/*` 토큰 응답은 제외합니다.
- `vercel.json`은 `Strict-Transport-Security: max-age=63072000; includeSubDomains`를 추가하고 옛 호스트 `photospot-nu.vercel.app`의 모든 경로를 `https://photospot.litaandd.com/$1`로 308 리다이렉트합니다. `www.photospot.litaandd.com`을 추가하면 Vercel Domains에서 리다이렉트 전용으로 둡니다.
- `/robots.txt`는 `/admin`·`/accounts`·`/oauth/`를 제외하고 `/sitemap.xml`을 가리킵니다. 사이트맵은 공개 페이지와 재사용 가능한 사진이 있는 장소 상세(`/place/{id}`)를 카탈로그에서 생성해 프로세스별로 캐시합니다.

### 관측

- 로그는 stdout에 JSON 한 줄(`ts, level, logger, msg, service, method, path, status, ms`)로 남습니다. 쿼리 문자열·본문·쿠키는 기록하지 않습니다. `LOG_LEVEL`(기본 INFO), `LOG_REQUESTS=0`(성공 요청 로그 끔)으로 조절합니다.
- `SENTRY_DSN`을 설정하면 `api.observability`가 FastAPI/Starlette 통합으로 Sentry를 초기화합니다. 환경은 `VERCEL_ENV`, 릴리스는 `VERCEL_GIT_COMMIT_SHA`를 사용합니다. `SENTRY_TRACES_SAMPLE_RATE`(기본 0)로 성능 추적을 켭니다.

### 익명 퍼널 이벤트

클라이언트는 `POST /preview/events`(회원 앱은 `/v1/events`)로 `{event, route, session_id, utm, props}`를 보냅니다. 허용 이벤트는 `landing_view, home_first_card, result_view, share_click, place_view, save, consent_accept, gps_allow`뿐이며, `route`는 쿼리 없는 경로, `session_id`는 브라우저가 만든 8~64자 무작위 값, `utm`은 `utm_source/medium/campaign/content/term`, `props`는 20개 이하의 작은 스칼라입니다. IP·User-Agent·계정 ID·생년월일은 받지도 저장하지도 않습니다. 저장소가 없거나 장애면 204로 버립니다. IP당 분당 `RATE_LIMIT_EVENTS_PER_MIN`(기본 60)회로 제한합니다.

최근 7일 세션 기준 퍼널:

```sql
WITH s AS (
  SELECT session_id,
         bool_or(event = 'landing_view')    AS landed,
         bool_or(event = 'home_first_card') AS first_card,
         bool_or(event = 'result_view')     AS result,
         bool_or(event = 'place_view')      AS place,
         bool_or(event IN ('save', 'share_click')) AS acted
  FROM analytics_events
  WHERE created_at >= now() - interval '7 days'
  GROUP BY session_id)
SELECT count(*) FILTER (WHERE landed)     AS landing,
       count(*) FILTER (WHERE first_card) AS first_card,
       count(*) FILTER (WHERE result)     AS result,
       count(*) FILTER (WHERE place)      AS place,
       count(*) FILTER (WHERE acted)      AS save_or_share
FROM s;
```

유입 경로별 비교는 `utm->>'utm_source'`로 그룹화합니다. 90일이 지난 행은 `DELETE FROM analytics_events WHERE created_at < now() - interval '90 days'`로 정리합니다. 개인정보처리방침이 밝힌 보관 기간에 맞춰 좋아요 기록도 마지막 활동일(`created_at`)로부터 12개월이 지나면 정리합니다: `PHOTO_LIKES_DATABASE_URL=<운영 DSN> python -m api.photo_likes prune` (= `DELETE FROM photo_likes WHERE created_at < now() - interval '12 months'` + 90일 지난 `analytics_events`). 월 1회 실행하고 결과 행 수를 기록합니다.

## 추천 시작 장소

현위치는 자동으로 조회하지 않습니다. 기본 시작 장소는 서울 종로·북촌이며, 홈의 '내 주변에서 찾기' → 위치정보 이용 동의 시트 → 기기/브라우저 권한 순서로만 1회 조회하고 좌표는 저장하지 않습니다. 동의 여부는 기기·브라우저에만 남습니다(서버 저장 없음). 권한 거부·시간 초과·수집 범위 밖 위치에서는 이전 장소를 유지하고 지원 지역(서울·부산·강릉·제주 일부)을 안내하며 임의의 서울 좌표로 조회하지 않습니다. 위치 확인 중 수동으로 고른 장소는 뒤늦은 위치 응답이 덮어쓰지 않습니다.

정책 문서(개인정보처리방침·이용약관·위치기반서비스 이용약관·계정 삭제 안내)는 `app/public/policies/*.html`이 빌드 때 `app/dist/policies/`로 복사되어 `/policies/*.html`로 JS 없이 제공됩니다(사이트맵 포함).

| 도시 | 선택할 수 있는 시작 권역 |
| --- | --- |
| 서울 · 7곳 | 종로·북촌, 성수·서울숲, 홍대·연남, 여의도·한강, 잠실·석촌호수, 남산·이태원, 강남·코엑스 |
| 부산 · 5곳 | 해운대·미포, 광안리, 남포·감천, 영도·흰여울, 송정·기장 해안 |
| 강릉 · 3곳 | 경포·초당, 안목·남항진, 주문진 |

권역은 촬영 여행을 위한 시작점이며 행정구역 경계 필터가 아닙니다. `app/src/recommendation-regions.ts`의 대표 좌표에서 기본 5km를 검색하고, 1·3·5·10·30·50km로 조절할 수 있습니다. 분류는 [서울 공식 관광정보](https://korean.visitseoul.net/attractions), [부산 공식 도보여행 안내](https://www.visitbusan.net/kr/index.do?lang_cd=ko&menuCd=DOM_000000202004001000&uc_seq=768), [한국관광공사의 주문진 안내](https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=174269)와 공개 장소 카탈로그를 참고해 구성했습니다.

위치 획득 실패와 비동기 요청 충돌 검증: `node app/scripts/test-starting-place.cjs`.

## 사진·공간·방문객 정합도

체형의 배경 형태, 170cm 기준 실내외 선호, 사진의 웜·쿨 색조,
최근 완료된 3개월 방문객 순위를 사용하는 카탈로그 정합도 v2를 적용합니다.
가중치·사진 검토 범위·통계 출처와 미집계 처리·갱신 절차는
[`pipeline/PROFILE_FIT.md`](../pipeline/PROFILE_FIT.md)에 정리되어 있습니다.
형태 검토 파일과 `catalog_visitors` 공개 테이블도 배포에 포함됩니다.
현재 2026-07~09 방문객 수는 확보된 비교 자료가 없어 미집계로 표시합니다.

## 달력과 종합 오행 추천

기본 추천과 오행·일진 추천의 촬영일은 같은 달력 컴포넌트에서 고릅니다. 기본 추천은 날짜 선택 즉시 조회하고, 오행 화면에서는 선택한 날짜와 저장된 오행으로 추천 보기 버튼을 누를 때 함께 계산합니다. 생년월일 입력과 촬영일 선택은 별도입니다.

공개 웹의 카탈로그 추천은 `personal70_daily30_v1` 기준을 사용합니다.

- 저장된 오행 비율의 반올림 합계를 100으로 정규화하고, 20% 미만인 오행을 보완 후보로 둡니다. 개인 보완 점수는 `max(0, 20 - 정규화 비율) / 20 × 70`입니다.
- 촬영일은 선택한 한국 달력 날짜 그대로 일주를 구하고, 일진 천간의 오행을 사용합니다. 일진→장소 상생 30점, 동일 24점, 장소→일진 상생 18점, 장소→일진 상극 6점, 일진→장소 상극 0점을 더합니다.
- 합계 상위 두 후보를 우선 대상으로 정하고, 두 번째 점수의 동점은 함께 포함합니다. 후보가 하나면 하나만 선택합니다. 개인 비율이 모두 같으면 개인 보완 점수는 0이고 전체 오행에서 일진 관계로 고릅니다.
- 장소에서 근거가 확인된 우선 대상 오행 중 최고 점수를 사용합니다. 여러 오행 태그를 합산해 점수를 부풀리지 않습니다. 근거 없는 오행은 부여하지 않으며, 우선 오행에 맞는 장소가 없으면 빈 결과를 안내합니다.
- 기본 추천과 오행 추천 모두 표시된 **전체 정합도 높은 순서 → 평가 완료 항목 수**로 정렬합니다. 이후 콘텐츠·운영 여부·사진 등 보조 조건으로 동점을 해소하며 정확한 순서는 `api/catalog_recommendations.py`의 `ranking_key`를 따릅니다. 오행 종합 점수는 기본 정합도에 합산하지 않습니다. 개인정보 없는 공개 둘러보기는 이 정렬 대신 사진 유무·운영 여부·기준점 거리 순서를 사용합니다.

상생·상극 방향은 [한국학중앙연구원 오행 해설](https://waks.aks.ac.kr/rsh/dir/rview.aspx?dataID=AKS-2013-CKD-1240001_DIC%4000015185&rshID=AKS-2013-CKD-1240001)을 참고했습니다. 20% 기준, 70:30 가중치와 관계별 점수는 포토스팟의 취향 탐색 설계이며 전통 명리의 용신 판정이나 효과가 검증된 사진 평가법을 뜻하지 않습니다. 기존 PostGIS 장면 채점 함수와 샘플 태그 엔진은 이 웹 카탈로그 정렬과 별도입니다.

검증: `node app/scripts/test-calendar.cjs`, `python -m pytest tests/test_deficient_recommendations.py -q`.

공개 서버의 입력 처리와 브라우저 저장 범위는 앱의 웹 체험 정보 처리 안내에서 확인할 수 있습니다. 실제 회원 서비스로 전환하려면 별도의 인증·DB·운영 정책 설정이 필요합니다.
