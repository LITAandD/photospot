# 추가 검토 16건 반영 (2026-10-12)

| 항목 | 반영 내용 |
| --- | --- |
| 1 진단 탈출 | 닫기·결과 적용이 같은 경로를 사용. 뒤로 갈 화면이 없으면 스타일 입력으로 이동. |
| 2 영업시간 삭제 | 활성 카페 0곳이면 즉시 중단. 기존 기록의 25% 초과 퇴역도 기본 중단. 카탈로그를 확인한 운영자만 `--allow-retire`로 예외 실행. |
| 3 부분 갱신 | 성공/부분 성공/전부 실패를 구분. 실패 지점의 기존 확인 날짜와 기록 보존. 일부 성공은 PR 생성까지 진행하고 실패 수를 경고·PR에 표시. 전부 실패는 실패 종료. 제한 수집의 미시도 지점도 부분 성공에 포함. |
| 4 요청 제한 | 서명·만료·토큰 종류·사용자 UUID를 검증한 액세스 토큰은 사용자별 집계. 비로그인 요청과 인증 경로의 별도 제한은 IP 기준. `/v1/health` 제외. |
| 5 웹 글꼴 | RN Web의 클래스에 맞지 않는 스타일 선택자 제거. 설치된 Expo 글꼴을 실제 별칭으로 등록하고 기본 시스템 글꼴 대체 경로 설정. |
| 6 응답 크기 | 목록은 대표 사진만 전달하고 상세 장소 사전은 비움. 저장 목록은 장소당 사진 1장, 상세는 `include_gallery=true`와 단일 ID로 갤러리 요청. gzip 적용. |
| 7 없는 페이지 | 한국어 `+not-found`, 자동 Sitemap 비활성화. 배포는 한국어 `404.html`을 404 상태로 반환. 알려진 페이지는 FastAPI에 명시적으로 등록해 CDN의 404 처리보다 우선. |
| 8 동의 우회 | 루트에서 세션 확인 후 보호 화면을 등록. 새 브라우저의 직접 링크는 공개 로그인 화면으로 이동하며 위치·추천 효과가 실행되지 않음. |
| 9 세션 종료 | 초기 인증 확인 중 보호 화면을 마운트하지 않음. 동시·지연 401의 로그아웃 알림을 세션당 한 번으로 제한. 실제 웹 자격 증명은 계속 메모리에만 저장. |
| 10 잘못된 장소 | 400/404/422는 재시도 대신 장소 없음 안내와 추천 목록 버튼. 네트워크·서버 오류만 재시도. |
| 11 중복·0점 | 같은 표시 그룹·이름이고 150m 이내인 중복 지도 지점은 가장 높은 순위 하나를 표시. 원본 데이터·저장 링크는 보존. 사주 목록은 확인된 기본 정합도 0점 제외. 미평가는 점수를 만들지 않음. |
| 12 감점 | 음수 분수 대신 “6점 감점”과 총점 차감 설명. 계산 자체는 유지. |
| 13 E2E | 실제 좌표의 기차바위 중복 레코드를 CI 전용 fixture에 추가. 사주 목록 정확히 1개·10점·상세 일치 검증. 빈 목록·산정 전을 허용하던 분기 제거. |
| 14 포즈 접근성 | 머리·발끝 위치를 사진 높이 백분율로 입력하고 키보드로 적용 가능. 범위·최소 간격 검사, 결과 라이브 알림. 원본 사진 이용 조건 유지. |
| 15 대표 사진 | 근경 → 미분류 → 원경 → 부적합 순서. 같은 등급에서는 출처 우선순위 보존. |
| 16 정리 | 제한 설정 문서 갱신, bluetooth 정책 제거, 입력 검증 요약 한국어화. 클라이언트 npm audit는 high/critical 차단, 낮은 등급도 보고서에 보존. |

## 검증

- 로컬 Python: 542 통과, 42 건너뜀. 실제 PostgreSQL/PostGIS 검사는 CI에서 수행.
- 클라이언트: 23개 테스트. 앱 타입 검사와 기존 앱 단위 검사 통과.
- Ruff, 제한된 범위의 mypy, 런타임 의존성 핀 일치 검사 통과.
- 새 회귀 검사: 빈/부분 카탈로그 보존, 부분 수집, 위조·만료 토큰과 동일 IP 사용자 격리, 갤러리 응답 분리·gzip, 한국어 404, 중복 장소 처리.
- CI 브라우저 검사에 직접 링크 동의 게이트, 진단 닫기/결과 적용, 등록 글꼴, 없는 장소·페이지, 키보드 포즈 보정 추가.
- 배포 카탈로그, 서울 기본 좌표, 여름 쿨·웨이브·INFP, 2026-10-12, 30곳 요청의 로컬 측정: 기존 전체 응답 1,409,500바이트 → 목록 JSON 150,260바이트 → gzip 약 11,833바이트. 사진 이미지 파일 다운로드는 별도이며 지역·프로필에 따라 크기가 달라짐.

## 적용 범위

공식 운영시간의 확인 날짜를 연장하거나 없는 방문객·사진 정보를 만들어 넣지 않았습니다. 제한기는 여전히 프로세스별 메모리이며 여러 인스턴스의 통합 한도는 별도 인프라가 필요합니다. 실제 인증 웹 세션의 새로고침 유지 기능은 추가하지 않았습니다. 브라우저 체험의 프로필·저장 목록과 동의를 거친 체험 세션은 유지됩니다. 모든 장소가 오행 미확인 또는 0점인 실제 검색 범위에서는 이유를 설명하는 빈 결과가 정상입니다.

## 2026-11-09 운영·보안 후속 (ops-security)

감사 항목 N-security-1, F094, N-ops-1/D-1/F039/N-data-1, N-data-2/D-2/F018, D-8, F068, F040에 대한 반영입니다. 데이터 파일(`pipeline/data/*.json`, `catalog/places.sqlite3`)은 바꾸지 않았습니다.

| 항목 | 반영 | 근거 |
|---|---|---|
| N-security-1 / F094 | `pillow` 13.0.0, `opentelemetry-api` 1.45.1, `certifi` 2026.10.18로 핀 상향(`constraints.txt`·`pyproject.toml` 일치). `pip_audit -r requirements.txt` 0건. npm 쪽과 같은 시간 제한 예외 파일 `security/python-audit-exceptions.json`(현재 0건)과 `scripts/check_python_audit.py`를 추가해 CI `security`가 유효한 예외만 `--ignore-vuln`으로 넘긴다. `decode-uri-component` 별칭 0.5.1, 빌드 전용 npm 권고 4건(deepmerge·glob·minimatch·zod)은 2026-12-09 만료 예외로 등록 | `tests/test_python_audit.py`, `scripts/check-app-audit.cjs --audit` exit 0, `tests/test_photo_likes.py`·`test_pipeline.py` 통과 |
| N-ops-1 / D-1 / F039 | `data-refresh.yml`: PR 생성 실패를 삼키던 `\|\| echo` 제거 → `::error`(설정 안내 포함)와 함께 작업 실패. `secrets.DATA_REFRESH_TOKEN`(fine-grained PAT)이 있으면 그 토큰으로 checkout·push·PR을 만들어 PR에서 CI가 돈다. 주 2회(월·목 06:17 KST) 실행 | 2026-10-18~11-09 실행 4건이 모두 'success'였지만 PR #17 이후 PR 없음, 브랜치 `data-refresh/official-hours`만 갱신됨 |
| D-2 / N-data-2 | 새 `data-freshness.yml`(매일 07:41 KST): 공식·검수 운영시간 만료 시 같은 제목의 이슈를 만들거나 갱신하고, 유효해지면 닫는다. `ci.yml` `test`에 `check_data_freshness --fail-within 7 --github` 비차단 경고 단계. `check_data_freshness`에 `--github`(stderr 주석)·`--markdown` 추가 | `tests/test_data_freshness.py` |
| F018 / N-data-2 (앱 표시) | 검수 영업시간이 30일을 넘기면 지도 등록시간이 최신일 때 그쪽을 보여 주고, 아니면 `영업시간 확인 필요 (YYYY-MM-DD 확인)`로 날짜와 함께 표시(시간표는 출처 확인용으로 유지) | `tests/test_place_hours.py` |
| D-8 | README·RELEASE_STATUS 운영 주소를 `photospot.litaandd.com`으로. 새 `deploy/OPERATIONS.md`: 환경변수 표(Vercel/Docker/앱/Actions secret), 감사 운영자 점검 14건 명령, 장애 대응(Neon·Vercel 504·만료 운영시간·PR 실패·CI 보안 실패), 백업·롤백, 브랜치 보호, 정기 작업 | — |
| F068 | 브랜치 보호 `gh api` 명령과 Vercel 배포 게이트를 OPERATIONS.md 6절에 기록 (설정 자체는 운영자 권한) | `branches/main/protection` → 404 (2026-11-09) |
| F040 | Dockerfile·docker-compose에 `FORWARDED_ALLOW_IPS` 안내 주석, OPERATIONS.md 2절에 LB 뒤 설정·검증 절차 | uvicorn 기본 `127.0.0.1,::1` |

미반영: 스타벅스 공식 사이트는 이 작업 환경에서 차단(프록시 403)되어 `python -m pipeline.official_place_hours --limit 3`은 `status: failed`로 끝났고 자료를 바꾸지 않았습니다. 검수 영업시간 9건의 `checked_at` 갱신은 출처 재확인이 필요해 운영자 작업으로 남깁니다.
