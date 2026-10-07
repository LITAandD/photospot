# 포토스팟 추천 API 서버 설계

참조 구현: `api/` (FastAPI + PostgreSQL/PostGIS). 명세 `openapi.yaml`은 코드에서 생성한다
(`python -m api.export_openapi > openapi.yaml`)이라 구현과 어긋나지 않는다.

## 1. 구성

```
앱 ──HTTPS/JWT──▶ API 서버 (무상태, 수평 확장)
                     │  SQL
                     ▼
              PostgreSQL + PostGIS ◀── 작업 처리기(worker) ── 파이프라인(색 분석 + Claude 비전)
              (장소·장면·규칙·추천 기록·작업 큐)          │
                     ▲                                 ▼
          정기 작업: TourAPI 수집, 인스타 트렌드 수집     객체 저장소 (사진 원본·분석용)
```

- **API 서버**: 요청당 트랜잭션 하나. 추천 점수는 DB 함수(`recommend_places_near`)가 계산하고, 서버는 결과를
  사람이 읽는 형태(이유·팁·라벨)로 바꾼다. 로직이 DB에 있어 서버는 얇고, 규칙 수정은 데이터 변경만으로 끝난다.
- **작업 큐**: 별도 인프라 없이 Postgres 테이블(`jobs`, `FOR UPDATE SKIP LOCKED`). 사진 업로드 → `analyze_spot`
  작업 → 처리기가 파이프라인 실행. 같은 스팟 작업은 대기열에 하나만 쌓인다. 트래픽이 커지면 Redis 큐로 교체.
- **외부 서비스**: 네이버는 딥링크만, 구글은 `place_id`만 저장하고 영업시간·리뷰는 앱이 직접 조회(약관상 서버 저장 금지),
  인스타는 해시태그 수치만 정기 수집.

## 2. 엔드포인트

| 메서드 | 경로 | 역할 |
|---|---|---|
| GET | `/v1/health` | 상태 확인 (인증 없음) |
| GET/PUT | `/v1/me/profile` | 프로필 (모든 항목 선택 입력) |
| POST/DELETE | `/v1/me/consents`, `/v1/me/consents/{type}` | 동의 부여·철회 |
| PUT/DELETE | `/v1/me/saju` | 사주 오행 비율·가장 많은 오행 계산(음력 지원)·삭제. 생년월일시와 네 기둥은 응답에만 쓰고 폐기 |
| GET | `/v1/me/type-card` | 결과 카드. `match_rules`에서 직접 뽑아 점수 로직과 항상 일치 |
| DELETE | `/v1/me` | 탈퇴: 개인정보·업로드 사진(파일 포함) 삭제, 계정 행은 탈퇴 표시로 남겨 토큰 재사용 차단 |
| GET | `/v1/recommendations` | 위치·날짜 기반 추천. 항목마다 `recommendation_id` (피드백 연결용) |
| GET | `/v1/places/{id}` | 장소 상세: 장면별 점수·이유, 촬영 팁, 운영 안내, 출처 표기된 사진 |
| POST | `/v1/recommendations/{id}/feedback` | 방문 여부·평점·태그 수정 제보 |
| POST | `/v1/photos` | 사진 업로드 (동의 필수) → 위치·기기 정보 제거 → 분석 작업 예약 |
| GET/POST | `/v1/diagnosis/{kind}/questions`, `/v1/diagnosis/{kind}` | 자가진단 문항·채점 (문항을 서버에 둬 앱 업데이트 없이 수정) |
| GET | `/v1/admin/review-queue` | 검수 대기열: 신뢰도 낮은 자동 장면 + 검수 이후 제보 3건 이상인 장면 |
| PATCH | `/v1/admin/scenes/{id}` | 태그 수정·검수 확정 (이후 자동 태깅이 덮어쓰지 않음) |

오류는 모두 `application/problem+json` (`{type, title, status, detail}`).

## 3. 인증 (소셜 로그인)

| 메서드 | 경로 | 역할 |
|---|---|---|
| POST | `/v1/auth/{google\|apple\|naver\|kakao}` | 서비스 토큰 검증 → 우리 액세스(1시간)·갱신(60일) 토큰. 처음이면 계정 생성 |
| POST | `/v1/auth/refresh` | 갱신 토큰 회전. 이미 쓴 갱신 토큰이 다시 오면 그 로그인 계열 전체 무효화 |
| POST | `/v1/auth/logout` | 이 기기의 갱신 토큰 무효화 |
| GET/POST/DELETE | `/v1/me/identities[/{provider}]` | 연결된 로그인 조회·추가·해제 (마지막 하나는 해제 불가) |

- 구글·애플은 ID 토큰을 각 사 공개키(JWKS)로 검증하고 aud·iss·nonce를 대조한다. 네이버·카카오는 사용자 정보 API로 확인하고, 카카오는 토큰의 앱 ID까지 대조한다.
- 액세스 토큰은 서버가 직접 발급·검증하는 JWT(HS256). `typ=access`가 아니면 거부. 관리자 권한은 `users.is_admin`에서 나온다.
- 저장하는 것: 서비스별 사용자 ID, 이메일(준 경우), 표시 이름. 서비스 액세스 토큰은 저장하지 않는다.
- `DEV_LOGIN=1`이면 `dev:<id>` 토큰을 구글 자리에 받아들인다 (Expo Go 개발용, 운영 금지).

## 4. 개인정보

- 사주: 생년월일시와 기둥은 저장하지 않는다. 오행 비율과 대표 오행만 남는다. 초기 결과 카드는 프로필만 사용하고, 추천/장소 상세 요청에 `use_saju=true`가 있을 때 대표 오행과 촬영일 일진의 천간 오행을 반영한다. `012_optional_daily_saju.sql` 적용이 필요하다.
- 사진: 업로드 시 GPS·기기 정보를 제거하고 촬영 시각만 남긴다. 사용자 사진은 분석에만 쓰고 다른 사용자에게 절대 노출하지 않는다
  (`cover_photo`는 직접 촬영·공공·사장님 사진만).
- 동의: `photo_analysis` 동의 없이는 업로드 불가, `saju` 동의 철회 시 사주 데이터 즉시 삭제.
- 탈퇴: 사진 파일까지 삭제하고 영향받은 장면을 재집계.
- 로그에 프로필 값·생년월일을 남기지 않는다 (요청 본문 로깅 금지).

## 5. 성능과 규모

- 추천은 **반경 안 장소를 공간 인덱스로 먼저 고른 뒤** 채점한다 (`recommend_places_near`). 반경 최대 50km.
- 채점 대상은 사진 근거(3장·신뢰도 0.6 이상) 또는 사람 확정 장면만 (008, `pipeline/INTEGRITY.md`). 분류·검색 테마 초기 태그는 채점되지 않는다.
- 채점은 후보 장면의 속성만 한 번 펼쳐 규칙과 조인한다 (006). 장소 600곳·장면 840개 기준 반경 추천 35ms, 전국 전체 채점 31ms.
- 장면이 수십만 개가 되면: 사용자 값의 조합이 유한하므로 장면별 `(차원, 사용자 값) → 점수`를 미리 계산해 두는 테이블로 바꾸면
  채점이 단순 합산이 된다.
- 응답 캐시 키: (프로필 `updated_at`, 방문일, 위치 격자, 반경, 시간대). 짧은 TTL(수 분)이면 충분.
- 속도 제한: 사용자당 분당 60회, 사진 업로드는 일 50장 권장 (게이트웨이나 Redis에서).

## 6. 실행

```bash
pip install korean_lunar_calendar fastapi uvicorn "psycopg[binary]" psycopg_pool pyjwt python-multipart pyyaml numpy pillow scikit-learn anthropic
psql -f schema.sql && psql -f migrations/002_pipeline.sql && psql -f migrations/003_api.sql && psql -f migrations/004_saju.sql && psql -f migrations/005_auth.sql
export DATABASE_URL=postgresql://... JWT_SECRET=... STORAGE_ROOT=./storage MEDIA_BASE_URL=https://cdn.example.com
uvicorn api.main:app --port 8000          # API
python -m api.worker                      # 작업 처리기 (ANTHROPIC_API_KEY 있으면 AI 판정 사용)
```

테스트: `DATABASE_URL=... python -m pytest tests -q`. DB 없이도 검증 가능한 회귀 검사는 실행되고 DB 통합 검사는 건너뜁니다. 최신 결과와 적용할 마이그레이션은 `../RELEASE_STATUS.md`와 `../deploy/RELEASE.md`를 확인하세요.

## 7. 미결 사항

- **사주 계산기**: `saju/` 패키지로 구현됨 (포스텔러 방식 궁성·조후 보정 + 합충 보정, 가장 많은 오행 선택). 자세한 한계는 `saju/README.md`.
- **사진 URL**: 참조 구현은 로컬 경로. 운영에서는 객체 저장소 + CDN, 사용자 사진은 서명 URL.
- **혼잡도**: 사진 기반 판정이 약하므로 방문자 통계 등 외부 데이터 연결 필요.
