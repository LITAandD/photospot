# 운영 안내 (환경변수·점검·장애 대응·복구)

운영 호스트는 `https://photospot.litaandd.com` (Vercel, 함수 리전 `icn1`)이며 옛 호스트 `photospot-nu.vercel.app`은 308로 넘어옵니다. 배포 절차는 [VERCEL.md](VERCEL.md), 출시 점검은 [RELEASE.md](RELEASE.md), 컨테이너 구성은 [README.md](README.md)를 보고, 이 문서는 **운영 중에 확인·조치할 것**만 모읍니다. 2026-11-09 감사(audit2) 운영자 체크리스트를 명령 그대로 옮겼습니다.

## 1. 환경변수

### Vercel (웹 체험 + `/preview/*`, `pyproject.toml` 의존성)

| 변수 | 운영값 | 비고 |
| --- | --- | --- |
| `PHOTO_LIKES_DATABASE_URL` | Neon **pooled** 연결 문자열 | 좋아요·사진 분석·익명 이벤트. 비우면 좋아요 비활성, 추천은 정상 |
| `PHOTO_LIKES_COOKIE_SECRET` | 32바이트 이상 무작위 | 익명 투표 쿠키 서명. 바꾸면 기존 쿠키가 모두 무효 |
| `PHOTO_LIKES_ORIGINS` | `https://photospot.litaandd.com` | 좋아요 쓰기를 허용할 Origin(쉼표 구분). 옛 호스트는 넣지 않음 |
| `PHOTO_LIKES_MIN_VOTES` / `PHOTO_LIKES_MIN_MARGIN` | 기본 `5` / `2` | 표가 대표사진·근거를 바꾸는 최소 표·여유분 |
| `PHOTO_LIKES_NEW_VOTERS_PER_DAY` / `PHOTO_LIKES_PER_DAY` | 기본 `30` / `200` | IP당 하루 새 쿠키·좋아요 수 (인스턴스별) |
| `SENTRY_DSN` | 프로젝트 DSN | 있을 때만 켜짐. 본문·쿼리스트링(좌표)·쿠키·IP 미전송. `SENTRY_ENVIRONMENT`(기본 `VERCEL_ENV`), `SENTRY_TRACES_SAMPLE_RATE`(기본 `0`) |
| `PUBLIC_BASE_URL` | `https://photospot.litaandd.com` | `robots.txt`·`sitemap.xml` 절대 주소 (기본값과 같으면 생략) |
| `LOG_LEVEL` / `LOG_REQUESTS` | 기본 `INFO` / `1` | stdout JSON 로그. 5xx는 `LOG_REQUESTS=0`이어도 남김 |
| `VERCEL=1`, `VERCEL_ENV`, `VERCEL_GIT_COMMIT_SHA` | 플랫폼 설정 | `VERCEL=1`일 때만 `x-forwarded-proto`·`x-real-ip`를 신뢰하고 좋아요 쿠키에 `Secure`를 붙임 |

확인: `vercel env ls production` 에 `PHOTO_LIKES_DATABASE_URL`, `PHOTO_LIKES_COOKIE_SECRET`, `PHOTO_LIKES_ORIGINS` 3개가 있어야 합니다. 값 추가는 `vercel env add <NAME> production` 후 재배포.

### Docker API·작업 처리기 (`requirements.txt` 전체 서버, [.env.example](../.env.example))

| 변수 | 운영값 | 비고 |
| --- | --- | --- |
| `APP_ENV` | `production` | 개발 기본값(JWT 비밀 등)을 거부 |
| `JWT_SECRET` | 32바이트 이상 무작위 | |
| `DATABASE_URL` | 관리형 PostgreSQL 16 + PostGIS | 기본 DB 암호는 개발 전용 |
| `CORS_ORIGINS` | 명시적 HTTPS 출처(쉼표) | 기본 `http://localhost:8081`은 개발 전용 |
| `DEV_LOGIN` | `0` | 반드시 0 |
| `FORWARDED_ALLOW_IPS` | LB·프록시의 IP/CIDR (쉼표) | 아래 2절. 비우면 `X-Forwarded-*`를 무시해 모든 사용자가 LB IP 하나로 집계됨 |
| `STORAGE_ROOT` / `MEDIA_BASE_URL` | 객체 저장소 마운트 / `/media` | 사용자 업로드를 공개 버킷에 두지 않음 |
| `RATE_LIMIT_AUTH_PER_MIN` 등 `RATE_LIMIT_*` | 기본 `60/240/120/30/60`, `RATE_LIMIT_IP_FACTOR=4` | 워커·인스턴스마다 따로 셈 |
| `PHOTO_LIKES_*`, `SENTRY_*`, `LOG_*`, `PUBLIC_BASE_URL` | Vercel 표와 동일 | |
| `GOOGLE_CLIENT_IDS`, `APPLE_*`, `KAKAO_APP_ID`, `NAVER_*`, `INSTAGRAM_*`, `REVENUECAT_SECRET_KEY`, `OPENAI_API_KEY` | 각 콘솔 값 | [GROWTH_SETUP.md](GROWTH_SETUP.md) |
| `ALLOW_OFFICIAL_BRAND_PHOTOS` | `0` | 서면 허락이 있을 때만 1 |
| `RECOMMENDATION_BACKEND` / `PLACE_CATALOG_DB` | `catalog` / 이미지 내 `catalog/places.sqlite3` | Dockerfile 기본값 |

### 앱 빌드 (`EXPO_PUBLIC_*`, [app/.env.example](../app/.env.example))

스토어·웹 빌드에는 절대 HTTPS 주소의 `EXPO_PUBLIC_PRIVACY_URL`, `EXPO_PUBLIC_TERMS_URL`, `EXPO_PUBLIC_LOCATION_TERMS_URL`, `EXPO_PUBLIC_ACCOUNT_DELETION_URL`과 `EXPO_PUBLIC_SUPPORT_EMAIL`이 있어야 `npm run check:release`가 통과합니다. 웹 체험은 `EXPO_PUBLIC_DEMO=1`, `EXPO_PUBLIC_DEV_LOGIN=0`. `EXPO_PUBLIC_*` 값은 번들에 포함되므로 서버 비밀을 넣지 않습니다.

### GitHub Actions secrets

| 이름 | 용도 |
| --- | --- |
| `DATA_REFRESH_TOKEN` (권장) | fine-grained PAT, 이 저장소만, **Contents: Read and write**, **Pull requests: Read and write**, 만료 ≤ 1년. `data-refresh`가 이 토큰으로 push·PR을 만들면 PR에서 `ci`가 자동 실행됩니다. 없으면 `GITHUB_TOKEN`을 쓰며 저장소 설정 Settings→Actions→General→Workflow permissions→**Allow GitHub Actions to create and approve pull requests**가 켜져 있어야 하고, 만들어진 PR은 CI가 돌지 않아 닫았다 다시 열어야 합니다. 만료 전 교체를 달력에 적어 두세요 |

## 2. 로드밸런서 뒤 `FORWARDED_ALLOW_IPS` (F040)

Dockerfile의 uvicorn은 `--proxy-headers`로 뜨지만 기본으로는 `127.0.0.1,::1`이 보낸 `X-Forwarded-For/-Proto`만 믿습니다. 컨테이너 앞에 LB·리버스 프록시가 있으면 모든 요청의 `request.client.host`가 LB 주소가 되어 `/v1/auth/*` 분당 60회 같은 IP별 한도를 전 사용자가 공유합니다 (`api/rate_limit.py`도 같은 변수를 읽습니다).

- `.env`(compose) 또는 컨테이너 환경에 **프록시가 쓰는 소스 주소만** 적습니다: `FORWARDED_ALLOW_IPS=10.0.1.0/24,10.0.2.0/24` (ALB·NLB 서브넷, 또는 nginx 컨테이너 IP). 운영에서 `*`는 쓰지 않습니다 — 누구나 헤더로 IP를 위조해 한도를 피할 수 있습니다.
- 검증: LB를 거쳐 `curl -s https://api.example/v1/health -H 'X-Forwarded-For: 203.0.113.9'`를 반복해 429가 호출자별로 걸리는지, 그리고 컨테이너 포트로 직접 같은 헤더를 보냈을 때 무시되는지(`LOG_REQUESTS=1` 로그의 client IP) 확인합니다.
- Vercel은 `VERCEL=1`로 플랫폼 헤더를 신뢰하므로 이 변수가 필요 없습니다.

## 3. 운영자 점검 목록 (감사 2026-11-09, 명령 그대로)

1. **좋아요 origin/쿠키 (D-3, D-11)**: `curl -si -X POST https://photospot.litaandd.com/preview/photo-likes/session -H 'Origin: https://photospot.litaandd.com' -H 'Sec-Fetch-Site: same-origin' -H 'Content-Type: application/json' -d '{}'` → 200 + `set-cookie: photospot_photo_voter=…; HttpOnly; Max-Age=31536000; Path=/; SameSite=lax; Secure` 기대. 403 '이 사이트에서만…'이면 `vercel env add PHOTO_LIKES_ORIGINS production` 값 `https://photospot.litaandd.com` 후 재배포. 503 '좋아요 저장소 연결을 준비하고 있어요'면 `PHOTO_LIKES_DATABASE_URL`/`COOKIE_SECRET` 누락, 503 '연결하지 못했어요'면 Neon 미도달/미마이그레이션(`python -m api.photo_likes` 1회). 음성 확인: 같은 명령에 `-H 'Origin: https://photospot-nu.vercel.app'` → 반드시 403.
2. **Neon 장애 시 추천 생존 (F006)**: Neon 콘솔에서 compute를 Suspend한 직후 `curl -s -o /dev/null -w '%{http_code} %{time_total}\n' -X POST https://photospot.litaandd.com/preview/evaluate -H 'Content-Type: application/json' -d '{"profile":{},"lat":37.5796,"lng":126.977,"visit_date":"2026-11-30","radius_m":5000}'` → 200(`likes_enabled=false`), 2초 안쪽 기대. 503 ~5초면 F006 패치 전 상태.
3. **함수 리전·Production env (F064, D-8)**: `vercel env ls production`에 `PHOTO_LIKES_DATABASE_URL`, `PHOTO_LIKES_COOKIE_SECRET`(≥32바이트), `PHOTO_LIKES_ORIGINS` 3개 존재; Vercel 대시보드 Settings→Functions→Region이 `icn1`(Seoul)인지; Neon 콘솔에서 프로젝트 리전(현재 Singapore)·플랜(Free)·autosuspend 지연·연결 한도 확인, 가능하면 서울/도쿄 근접 리전으로 재생성.
4. **보안 헤더/HSTS/정적 캐시 (D-7, F033)**: `curl -sI https://photospot.litaandd.com/home | grep -iE 'strict-transport|content-security|x-frame|referrer|cache-control'`; 그리고 `ENTRY=$(curl -s https://photospot.litaandd.com/ | grep -o '/_expo/static/js/web/entry-[^"]*\.js' | head -1); curl -sI "https://photospot.litaandd.com$ENTRY" | grep -i cache-control` → `strict-transport-security max-age≥63072000`, 정적 JS는 `immutable` 기대(`no-store`면 F033 라이브 재현).
5. **호스트 정규화 (D-4)**: `curl -sI https://photospot-nu.vercel.app/home | head -3` (308 + `location: https://photospot.litaandd.com/home` 기대); `curl -sI http://photospot.litaandd.com/ | head -3` (308 → https); `curl -sI https://www.photospot.litaandd.com/ | head -3` (NXDOMAIN 또는 308, 절대 200 아님).
6. **딥링크/404/함수 번들 (S-7, F030, D-11)**: `for p in /home /place/4d5e3cfe-6207-5436-b374-ad875122406f /place/does-not-exist /privacy /oauth/naver /nonexistent /robots.txt /favicon.ico /manifest.json; do curl -s -o /dev/null -w "$p %{http_code} %{content_type}\n" https://photospot.litaandd.com$p; done` → 라우트 200 `text/html`, `/nonexistent` 404; 어떤 라우트든 503 '웹 화면을 준비하고 있어요'면 `vercel.json` `functions.includeFiles`에 `deploy/vercel/web-entry.html` 누락.
7. **데이터 신선도 라이브 (N-ops-1, D-1)**: `curl -s https://photospot.litaandd.com/health`; `curl -s -X POST https://photospot.litaandd.com/preview/evaluate -H 'Content-Type: application/json' -d '{"profile":{},"lat":37.5796,"lng":126.977,"visit_date":"2026-11-30","radius_m":5000,"place_ids":["4d5e3cfe-6207-5436-b374-ad875122406f","0c2fc87c-7956-51b8-a95b-3c9c6030409f","cf6a3977-440f-5e2b-94f2-74ee49f48c16"]}' | jq '.places[].hours | {checked_at, stale, summary}'` → 갱신 PR 병합·재배포 후 `checked_at`이 최근 월/목, `stale false` 기대. `stale true`면 4절 '만료된 운영시간'.
8. **GitHub Actions PR 권한·갱신 복구 (D-1, F094)**: `DATA_REFRESH_TOKEN` secret 등록(1절) 또는 Settings→Actions→General→Workflow permissions→'Allow GitHub Actions to create and approve pull requests' 체크. 그다음 `gh workflow run data-refresh.yml -R LITAandD/photospot`; 완료 후 PR이 자동으로 열리는지 확인(`gh pr list -R LITAandD/photospot --head data-refresh/official-hours`). 열리지 않았으면 run 로그의 `::error` 안내대로 `gh pr create -R LITAandD/photospot --base main --head data-refresh/official-hours --title 'data: 공식 지점 운영시간 갱신'`. 이어서 `gh run list -R LITAandD/photospot --workflow ci.yml -L 1`로 `test`·`app`·`security` 녹색 확인.
9. **의존성 감사 로컬 재현 (N-security-1)**: `python -m pip_audit -r requirements.txt --progress-spinner off $(python -m scripts.check_python_audit --ignore-args)`; `cd app && npm audit --json > /tmp/a.json && cd .. && node scripts/check-app-audit.cjs --audit /tmp/a.json` → 둘 다 exit 0이 될 때까지 프로덕션 배포 금지. 예외 목록(`security/*.json`)의 `review_after`가 지나면 게이트가 다시 빨개지므로 그 전에 재검토·핀 상향.
10. **브랜치 보호·배포 게이트 (F068)**: 6절 명령으로 `main`에 `test`·`app`·`security` 필수 검사를 걸고, Vercel Settings→Git에서 'Ignored Build Step' 또는 Deployment Protection으로 CI 실패 커밋이 프로덕션에 올라가지 않는지 확인.
11. **부하 테스트 (F005)** — 패치 배포 후 트래픽 적은 시간에: `/tmp/claude-0/audit/ops/load.py`의 인자(베이스 URL·동시성)를 확인해 `python /tmp/claude-0/audit/ops/load.py --base https://photospot.litaandd.com --conc 8` 로 실행 → p50 < 2초, 504 0건 기대; Vercel Firewall에 `/preview/*` 60 req/min/IP 규칙 생성 후 동일 테스트로 429 동작 확인.
12. **오류 추적·업타임 (F041, F044)**: Vercel env에 `SENTRY_DSN`(API)·`EXPO_PUBLIC_SENTRY_DSN`(웹) 추가 후 `curl -s -X POST https://photospot.litaandd.com/preview/evaluate -H 'Content-Type: application/json' -d 'not-json'` 로 422/500 이벤트가 Sentry에 찍히는지 확인; 외부 업타임(UptimeRobot 등)에 `https://photospot.litaandd.com/health` 1분 간격 + 503/타임아웃 알림 채널(카카오/슬랙) 연결. 모니터는 `likes.reachable`도 함께 봅니다(`/health`는 저장소 장애에도 200).
13. **법무·행정 (F007, F008, F036)**: 방통위 위치기반서비스사업 신고(개인/소상공인 간이신고) 접수번호 확보 — 완료 전엔 홈 마운트 시 자동 GPS 호출을 꺼둔 상태로 운영; 처리방침에 기재할 운영자 성명·연락처·Vercel(미국)·Neon(싱가포르) 보유기간을 확정해 `app/public/policies/*.html`에 반영; IAP를 켜기 전 통신판매업 신고 또는 면제(연 거래 50회·4,800만원 미만) 해당 여부 확인.
14. **브라우저 DevTools 확인 (D-11)**: `https://photospot.litaandd.com/place/4d5e3cfe-6207-5436-b374-ad875122406f`에서 Application→Cookies `photospot_photo_voter`가 HttpOnly·Secure·SameSite Lax·host-only(photospot.litaandd.com)인지; Network의 `POST /preview/photo-likes/session` 요청 헤더에 `origin`·`sec-fetch-site: same-origin`; Console에 CSP img-src 위반 0, 위키미디어 썸네일 429/403 없음.

## 4. 장애 대응

### Neon(좋아요 저장소) 장애

증상: `/health`의 `likes.reachable=false`, 좋아요 버튼 비활성 또는 쓰기만 `503 좋아요 저장소에 연결하지 못했어요`, 로그에 분당 1회 `photo_likes` 연결 실패. 추천·장소 상세는 `likes_enabled=false`로 계속 응답해야 합니다(2초 타임아웃, 20초 회피).

1. 범위 확인: `curl -s https://photospot.litaandd.com/health | jq .likes`; 3절 2번 명령으로 추천이 200인지. 추천까지 느리면 Vercel 504 절차로.
2. Neon 콘솔 → 프로젝트 → Branches/Compute 상태(Idle/Active, 오류), Operations 탭, Monitoring의 연결 수. Free 플랜 autosuspend 깨우기 지연(수 초)은 장애가 아니라 정상 지연입니다.
3. 연결 한도 초과면 pooled(`-pooler`) 호스트를 쓰고 있는지 `vercel env ls production`에서 확인(인스턴스당 최대 3연결).
4. 자격 증명 재발급·리전 이전 시: 새 연결 문자열로 `PHOTO_LIKES_DATABASE_URL` 교체 → `python -m api.photo_likes`(테이블 생성, 멱등) → 재배포 → 3절 1번 재확인.
5. 장애 중 계정 삭제가 있었으면 ERROR 로그의 `voter_hash`로 복구 후 `python -m api.photo_likes revoke <voter_hash>`.

### Vercel 504 / 느린 추천

1. `curl -s -o /dev/null -w '%{http_code} %{time_total}\n' https://photospot.litaandd.com/health` 와 3절 2번(추천) 소요 시간을 비교. `/health`만 빠르면 함수 내부(좋아요 저장소 대기 또는 카탈로그 적재), 둘 다 느리면 플랫폼.
2. Vercel 대시보드 → Deployments → 현재 Production → Functions 로그에서 `deploy/vercel/index.py` 오류·`maxDuration`(60초) 초과·콜드스타트 시간 확인. Sentry에 5xx 이벤트가 있으면 스택을 먼저 봅니다.
3. Neon 쪽 지연이면 위 Neon 절차. 저장소 회피(20초)가 동작하면 추천은 200이어야 하며 아니면 F006 회귀입니다.
4. 최근 배포가 원인이면 5절의 즉시 롤백. 플랫폼 장애는 `https://www.vercel-status.com`을 확인하고 기다립니다.
5. 트래픽 급증이면 Vercel Firewall에서 `/preview/*` IP당 60 req/min 규칙을 켭니다(3절 11번).

### 만료된 운영시간 (official_place_hours / place_hours)

앱 동작: 공식 날짜별 시간(스타벅스 3곳)은 게시된 마지막 날짜가 지나면, 검수 영업시간(`pipeline/data/place_hours.json`)은 확인 후 30일이 지나면 **사실처럼 보여 주지 않습니다** — 지도 등록시간이 30일 이내면 그쪽을, 아니면 `영업시간 확인 필요 (YYYY-MM-DD 확인)`/`촬영일 운영시간 · 공식 안내 확인`을 표시합니다. 그래서 만료는 장애가 아니라 데이터 품질 저하이며, `data-freshness` 워크플로가 매일 같은 제목의 이슈를 만들거나 갱신합니다.

1. 현황: `python -m scripts.check_data_freshness` (로컬, 네트워크 없음). CI `test` 작업의 'Data freshness (warning only)' 주석과 같은 내용입니다.
2. 공식 날짜별 시간: `gh workflow run data-refresh.yml -R LITAandD/photospot` → 완료 후 열린 PR(`data: 공식 지점 운영시간 갱신`)의 `artifacts` 보고서(성공/실패 지점 수) 확인 → 병합 → Vercel이 main을 다시 배포 → 3절 7번으로 `stale false` 확인. 스타벅스가 403/429를 돌려주면 수집이 멈추고 기존 기록을 보존하므로 다음 날 다시 실행합니다. 샌드박스·사내망에서 `www.starbucks.co.kr`이 막혀 있으면 `python -m pipeline.official_place_hours --limit 3`은 `status: failed`로 끝나고 자료를 바꾸지 않습니다 — 데이터를 손으로 적지 않습니다.
3. 검수 영업시간: `pipeline/data/place_hours.json`의 각 항목을 `source_url`(네이버지도)에서 다시 확인하고, 바뀐 시간은 `week`/`seasonal_hours`/`monthly_closures`에 반영한 뒤 `checked_at`을 **실제로 확인한 날짜**로 갱신해 PR. 확인하지 않은 항목의 날짜만 올리지 않습니다. 궁·박물관처럼 계절표가 있는 곳은 분기마다 묶어서 확인하면 됩니다.
4. 이슈는 다음 날 점검에서 자료가 모두 유효하면 자동으로 닫힙니다.

### data-refresh PR 생성 실패

run 로그 끝에 `::error title=PR 생성 실패`가 있으면 브랜치는 push됐지만 PR이 없습니다. 1절의 `DATA_REFRESH_TOKEN`을 등록하거나 'Allow GitHub Actions to create and approve pull requests'를 켠 뒤, 당장은 `gh pr create -R LITAandD/photospot --base main --head data-refresh/official-hours --title 'data: 공식 지점 운영시간 갱신'`으로 수동 생성합니다.

### CI `security` 작업 실패 (새 CVE)

`pip_audit`/`npm audit`에 상류 CVE가 새로 뜨면 게이트가 빨개집니다. 수정 버전이 있으면 `constraints.txt`+`pyproject.toml`(둘 다, `python -m scripts.check_dependencies`) 또는 `app/package-lock.json`을 올립니다. 없으면 `security/python-audit-exceptions.json` / `security/app-audit-exceptions.json`에 근거·완화책과 `review_after`(Python 최대 45일, npm 30일 권장)를 적어 시간 제한 예외로 등록합니다. 예외를 개수로 통과시키지 않습니다.

## 5. 백업·롤백

| 대상 | 백업 | 복구/롤백 |
| --- | --- | --- |
| 웹·`/preview` (Vercel) | 모든 배포가 불변 스냅샷으로 남음 | 대시보드 Deployments → 직전 정상 배포 → **Instant Rollback**(또는 `vercel rollback <deployment-url>`), 수 초 내 반영. 롤백 후 원인 커밋을 `git revert`해 main을 맞춤 |
| 좋아요·이벤트 (Neon) | 플랜별 PITR 이력(Free 1일 내외, Launch 7일+) + 수동 `pg_dump` | Neon 콘솔 → Branches → **Restore**(시점 선택)로 새 브랜치/복원 → 연결 문자열 교체 후 재배포. 구조만 필요하면 `python -m api.photo_likes` |
| 장소 카탈로그·운영시간 | git(`catalog/places.sqlite3`, `pipeline/data/*.json`) | 잘못된 데이터 PR은 `git revert` 후 push → Vercel 자동 재배포 |
| Docker API 이미지 | `ghcr.io/litaandd/photospot:<sha>`(CI가 main마다 push) | 직전 SHA 태그로 재배포. 마이그레이션은 하위 호환으로 작성하므로 코드만 되돌릴 수 있음 |
| 운영 DB (Docker 구성) | 관리형 PostgreSQL 일일 스냅샷 + PITR | 공급자 콘솔 복원 → `DATABASE_URL` 교체 → `python -m scripts.migrate --status` |

분기 1회 복구 연습(Neon Restore로 테스트 브랜치 만들어 `SELECT count(*)` 확인, Vercel 롤백 1회)을 권장합니다.

## 6. 브랜치 보호 (F068)

현재 `main`은 보호되지 않아(`gh api repos/LITAandD/photospot/branches/main/protection` → 404) push 즉시 Vercel이 운영에 배포합니다. `ci.yml`의 작업 이름(`test`, `app`, `security`)을 필수 검사로 겁니다:

```sh
gh api -X PUT repos/LITAandD/photospot/branches/main/protection -H 'Accept: application/vnd.github+json' --input - <<'JSON'
{"required_status_checks":{"strict":true,"contexts":["test","app","security"]},
 "enforce_admins":false,"required_pull_request_reviews":null,"restrictions":null,
 "allow_force_pushes":false,"allow_deletions":false}
JSON
```

- `data-refresh`가 `GITHUB_TOKEN`으로 만든 PR은 CI가 돌지 않아 필수 검사를 통과할 수 없습니다 — `DATA_REFRESH_TOKEN`(1절)을 먼저 등록하세요.
- Vercel Settings→Git→'Ignored Build Step' 또는 Deployment Protection으로 CI 실패 커밋이 프로덕션에 올라가지 않게 합니다.
- 작업 이름을 바꾸면 보호 규칙의 `contexts`도 함께 바꿔야 합니다.

## 7. 정기 작업

| 주기 | 작업 | 위치 |
| --- | --- | --- |
| 월·목 06:17 KST | 공식 날짜별 운영시간 재수집 → PR | `.github/workflows/data-refresh.yml` |
| 매일 07:41 KST | 자료 만료 점검 → 이슈 생성/갱신/닫기 | `.github/workflows/data-freshness.yml` |
| PR·push마다 | 7일 내 만료 경고(비차단), pip-audit·npm audit 게이트 | `.github/workflows/ci.yml` |
| 주 1회 | `pip_audit`·`npm audit` 결과와 `security/*.json`의 `review_after` 확인 (현재 npm 예외 4건 2026-12-09 만료) | 3절 9번 |
| 분기 | 검수 영업시간 재확인, Neon/Vercel 복구 연습, PAT 만료일 | 4·5절 |
