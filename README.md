# 포토스팟 — 나에게 어울리는 촬영 장소 추천

Expo Android/iOS 앱 + FastAPI + PostgreSQL/PostGIS 프로젝트입니다. 선택한 퍼스널컬러·체형·키·MBTI·사주 오행을 바탕으로 사진 촬영 장소를 추천합니다.

웹 체험 버전은 [photospot-nu.vercel.app](https://photospot-nu.vercel.app/home)에 배포되어 있습니다. 설치형 앱은 **1.0 출시 후보**입니다. 오류 수정과 실행 검증 결과는 [RELEASE_STATUS.md](RELEASE_STATUS.md), 운영 연결·스토어 배포 절차와 미검증 범위는 [출시 점검 문서](deploy/RELEASE.md)를 먼저 확인하세요. 실제 스토어 제출은 별도입니다.

앱 시작: `npm --prefix client ci`, `npm --prefix client run build`, `npm --prefix app ci`, `npm --prefix app start`.

브라우저에서 공유할 웹 체험 버전은 [Vercel 배포 안내](deploy/VERCEL.md)를 참고하세요. 웹 화면과 추천·사주 계산을 같은 Vercel 주소에서 제공하며, 프로필과 저장 목록은 각 브라우저에 보관합니다.

## 장면 태그 자동 생성 파이프라인

사진 → 장면(스팟 × 시간대 × 계절) 태그를 자동으로 만들어 `scenes` 테이블에 저장한다.

## 흐름

1. **사진 등록**: TourAPI(공공누리 1·3유형만), 직접 촬영, 사장님·사용자 업로드
2. **사진 1장 분석** (`aggregate.analyze_photo`)
   - 인물 마스킹 (선택, `--mask rembg`)
   - 색 분석: CIELAB 통계 → 색온도·명도·채도 (규칙 기반, `color.py`)
   - AI 판정: 조명·형태·질감·스케일·혼잡도·성격·무드·보이는 요소·계절 요소 (`vision.py`)
   - 시간대: EXIF 촬영 시각 > AI 판정 > 색 통계 순으로 결정
3. **장면 집계** (`aggregate.aggregate`): 같은 스팟·시간대·계절 사진끼리 묶어 가중 투표
   - 출처 가중치: 직접 촬영 1.0 > TourAPI 0.9 > 사장님 0.8 > 사용자 0.7
   - 신뢰도 = 태그 일치율 평균 × 사진 수 감쇠 (5장 미만이면 감쇠)
4. **저장** (`db.upsert_scene`): 자동 태그만 갱신, 사람이 입력·검수한 장면(manual/verified)은 보존
5. **검수**: 신뢰도 0.6 미만이거나 문제가 있는 장면은 `scene_review_queue` 뷰로
6. **보정**: 검수 완료 장면이 쌓이면 `calibrate`로 색 기준값 재조정

## 설치 · 실행

Python 3.12~3.14와 Node 22를 사용합니다. 저장소 루트에서 실행하세요.

```sh
python -m venv .venv
```

가상환경 활성화: Windows PowerShell은 `.\.venv\Scripts\Activate.ps1`, macOS/Linux는 `source .venv/bin/activate`입니다. 이후 명령은 두 환경에서 같습니다.

```sh
python -m pip install -r requirements-dev.txt -r requirements-quality.txt
npm --prefix client ci
npm --prefix client run build
npm --prefix app ci
npm --prefix app run demo -- --port 8081
```

웹 체험은 공개 `catalog/places.sqlite3` 스냅샷을 사용하며 PostgreSQL 없이 실행할 수 있습니다. 개인 프로필과 저장 목록은 브라우저에만 보관합니다.

인증 API 개발은 `.env.example`을 `.env`로 복사하고 개발용 값을 설정한 뒤 `docker compose up --build -d`로 시작합니다. 이미 실행 중인 PostgreSQL/PostGIS를 사용한다면 `DATABASE_URL` 환경 변수를 설정하고 `python -m scripts.migrate --seed`로 전체 마이그레이션을 순서대로 적용합니다. 운영 DB에는 테스트용 seed를 넣지 않습니다. 일부 SQL 파일만 수동 적용하는 예전 설치 방법은 사용하지 않습니다.

검사: `python -m pytest tests -q`, `npm --prefix client test`, `npm --prefix app run typecheck`, `npm --prefix app test`. `make test`는 의존성 일치·Python 정적 검사와 이 핵심 검사를 함께 실행합니다. DB 미설정 시 DB 통합 검사는 생략되며, [GitHub CI](https://github.com/LITAandD/photospot/actions/workflows/ci.yml)는 PostGIS와 브라우저를 포함해 검사합니다.

런타임 버전의 기준은 `constraints.txt`이며 `pyproject.toml`은 Vercel에 필요한 작은 부분집합입니다. `python -m scripts.check_dependencies`가 두 설정의 버전 차이를 차단합니다.

## 운영 팁

- **비용**: 대량 초기 태깅은 `vision.build_batch_requests()`로 Message Batches API를 쓰면 저렴하다.
  사진은 1024px로 줄여 보낸다. 기본 모델은 Haiku 4.5, 검수 대기열에 자주 걸리는 장면만 상위 모델로 재분석.
- **공공누리 3유형**은 변경 금지라 앱 화면에서 자르지 말고 원본 비율로 보여줄 것.
- **혼잡도**는 사진이 한산할 때 찍히는 경향이 있어 AI 판정이 약하다. 나중엔 방문자 통계 등 다른 데이터로 대체 권장.
- **일출·일몰표**는 서울 기준이라 제주·강원 등은 ±20분 오차. 지역이 늘면 위경도로 계산하는 방식으로 교체.

## 알려진 한계

- 색 기준값은 합성 이미지로 잡은 초기값이다. 실제 사진 수백 장을 검수한 뒤 `calibrate`로 반드시 보정할 것.
- `RembgHumanMask`(인물 마스킹)는 인터페이스만 검증했고, 실제 모델로는 테스트하지 않았다.
- TourAPI 요청 파라미터는 활용매뉴얼 최신판으로 확인 필요. 이 환경에서는 실제 호출을 못 해서 응답 파싱만 테스트했다.

---

# 프로젝트 전체 구성

| 폴더 | 내용 | 문서 |
|---|---|---|
| `schema.sql`, `migrations/` | DB 스키마와 마이그레이션 (PostgreSQL + PostGIS) | — |
| `pipeline/` | 사진 → 장면 태그 파이프라인, 정합성 점검, TourAPI·네이버·인스타 수집 | `pipeline/INTEGRITY.md`, `BULK_IMPORT.md`, `CAFE_SOURCES.md` |
| `saju/` | 사주 오행 계산기 (포스텔러 방식 보정) | `saju/README.md` |
| `api/` | 추천 API 서버 (FastAPI) + 작업 처리기 | `api/README.md`, `openapi.yaml` |
| `client/` | 앱용 TypeScript 클라이언트 | `client/README.md` |
| `app/` | Expo(React Native) 앱 | `app/README.md` |
| `Dockerfile`, `docker-compose.yml`, `.github/workflows/ci.yml`, `scripts/migrate.py` | 배포·CI | `deploy/README.md` |

빠른 시작: `cp .env.example .env && docker compose up --build -d` → `curl localhost:8000/v1/health`
