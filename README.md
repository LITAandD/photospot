# 포토스팟 — 나에게 어울리는 촬영 장소 추천

Expo Android/iOS 앱 + FastAPI + PostgreSQL/PostGIS 프로젝트입니다. 선택한 퍼스널컬러·체형·키·MBTI·사주 오행을 바탕으로 사진 촬영 장소를 추천합니다.

현재 버전은 **1.0 출시 후보**입니다. 오류 수정과 실행 검증 결과는 [RELEASE_STATUS.md](RELEASE_STATUS.md), 운영 연결·스토어 배포 절차와 미검증 범위는 [출시 점검 문서](deploy/RELEASE.md)를 먼저 확인하세요. 실제 스토어 제출은 별도입니다.

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

```bash
pip install numpy pillow scikit-learn "psycopg[binary]" anthropic
psql -f schema.sql && psql -f migrations/002_pipeline.sql

export DATABASE_URL=postgresql://...  STORAGE_ROOT=./storage  ANTHROPIC_API_KEY=...  TOURAPI_KEY=...
python -m pipeline.run import-tourapi --spot <spot_id> --content-id <TourAPI contentId>
python -m pipeline.run analyze                    # 미분석 사진 전체
python -m pipeline.run analyze --spot <id> --mask rembg   # 사용자 업로드처럼 인물이 큰 사진
python -m pipeline.run calibrate                  # 검수 사진 30장 이상 쌓인 뒤
```

테스트: `DATABASE_URL=... python -m pytest tests -q` (DB가 없으면 DB 통합 테스트는 건너뜀)

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
