# 배포 구성

현재 앱 출시 절차와 남은 검증은 [RELEASE.md](RELEASE.md), 실제 로컬 검사 결과는 [RELEASE_STATUS.md](../RELEASE_STATUS.md)를 먼저 확인하세요.

## 개발·스테이징 (한 대의 서버)
```bash
cp .env.example .env && vi .env      # JWT_SECRET 등 채우기
docker compose up --build -d          # db → migrate → api + worker
curl localhost:8000/v1/health
```
`migrate` 서비스가 스키마와 마이그레이션(적용된 것은 건너뜀)을 돌린 뒤에야 api·worker가 뜬다.
API와 작업 처리기는 같은 이미지에서 명령만 다르다.

## CI (GitHub Actions, `.github/workflows/ci.yml`)
1. 빈 PostGIS 컨테이너에 마이그레이션 → 전체 서버 테스트 실행
2. `openapi.yaml`이 코드와 다르면 실패 (명세 갱신을 잊지 않게)
3. 앱 타입·클라이언트 회귀 검사·Android/iOS/웹 번들·데모 UI 검사
4. 위 검사 통과 후 `main`에 머지되면 이미지를 `ghcr.io`에 push (`latest`, 커밋 SHA 태그)

## 운영 (권장 구성)
| 구성요소 | 권장 | 이유 |
|---|---|---|
| DB | 관리형 PostgreSQL 16 + PostGIS (AWS RDS 서울, NCP Cloud DB 등) | 자동 백업·장애 조치. 스토리지 자동 확장 |
| API | 컨테이너 2대 이상 (ECS/Fargate, NCP Kubernetes, 또는 VM + compose) | 무상태라 수평 확장. 앞에 로드밸런서 + HTTPS |
| 작업 처리기 | 컨테이너 1대부터 (`python -m api.worker`) | 큐가 쌓이면 대수만 늘림 (SKIP LOCKED로 중복 없음) |
| 사진 저장소 | S3 호환 객체 저장소 + CDN | `STORAGE_ROOT`를 마운트 대신 객체 저장소 어댑터로 교체 (`pipeline/tourapi.py`의 `LocalStorage`와 같은 인터페이스) |
| 비밀 | SSM Parameter Store / Vault / GitHub Secrets | `.env` 파일을 이미지에 넣지 않는다 |

### 배포 순서
1. 새 이미지 push → 2. `python -m scripts.migrate` (마이그레이션은 하위 호환으로 작성, 컬럼 삭제는 두 단계로) → 3. API 롤링 교체 → 4. 작업 처리기 교체
`scripts/migrate.py --status`로 적용 현황을 확인할 수 있다.

### 운영 체크리스트
- `JWT_SECRET`: 32바이트 이상 임의 값. `GOOGLE_CLIENT_IDS`, `APPLE_AUDIENCES`, `KAKAO_APP_ID` 설정. `DEV_LOGIN`은 운영에서 반드시 0
- 로그인 엔드포인트(`/v1/auth/*`)는 IP당 분당 10회로 더 엄격하게 제한
- 속도 제한: 로드밸런서·API 게이트웨이에서 사용자당 분당 60회, 사진 업로드 일 50장
- 백업: DB 일일 스냅샷 + PITR, 객체 저장소 버전 관리
- 로그: 요청 본문(프로필·생년월일)은 남기지 않는다. 사진 경로에는 사용자 ID가 없다
- 모니터링: `/v1/health`, `jobs` 테이블의 `queued` 적체 수, `failed` 수
- 정기 작업(크론): TourAPI 수집, 인스타 트렌드 수집, `python -m pipeline.run calibrate`
