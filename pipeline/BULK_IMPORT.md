# 장소 500곳 이상 채우기 (TourAPI 일괄 수집)

## 1. 준비
- [공공데이터포털](https://www.data.go.kr)에서 "한국관광공사_국문 관광정보 서비스_GW" 활용 신청 → 인증키 (`TOURAPI_KEY`)
- 개발 계정은 하루 1,000회 호출. 목록 1회에 최대 100건이라 500곳 수집엔 20~40회면 충분 (사진 내려받기는 호출 수에 포함되지 않음)
- 서버·DB가 떠 있어야 함 (`docker compose up -d` 또는 로컬)

## 2. 실행
```bash
export TOURAPI_KEY=... DATABASE_URL=... STORAGE_ROOT=./storage
# 서울·부산·제주의 관광지·문화시설에서 500곳
python -m pipeline.run import-tourapi-bulk --areas 1,6,39 --types 12,14 --target 500
# 전국, 카페까지 (39 = 음식점, 카페 소분류 포함)
python -m pipeline.run import-tourapi-bulk --types 12,14,39 --target 2000
```
지역 코드: 1 서울, 2 인천, 3 대전, 4 대구, 5 광주, 6 부산, 7 울산, 8 세종, 31 경기, 32 강원, 33 충북, 34 충남, 35 경북, 36 경남, 37 전북, 38 전남, 39 제주

## 3. 무엇이 만들어지나
항목 하나마다:
- `places` (이름·좌표·시도·시군구·주소, 상태 `unverified`) + `place_external_ids` (TourAPI contentid)
- `spots` "대표 지점" 하나
- **분류 코드 기반 초기 장면** (`tag_source=auto`, 신뢰도 0.3, 검수 대기열에 등록). 해수욕장은 낮+골든아워, 전망대·건물은 낮+야경처럼 2개가 생기는 분류도 있음
- 대표 사진 1장 (`cpyrhtDivCd`가 1·3유형인 것만. 2·4유형과 미표기는 장소 자체를 건너뜀)
- `analyze_spot` 작업 → 작업 처리기가 사진을 분석해 초기 태그를 덮어씀

실제 데이터에서는 사진 없음·라이선스 제외로 약 20~25%가 걸러지므로 `--target`은 '추가된 장소 수' 기준으로 센다.

## 4. 이후
- 작업 처리기 실행: `python -m api.worker` (ANTHROPIC_API_KEY가 있으면 AI 판정 포함)
- 검수: `/v1/admin/review-queue`에 초기 태그 장면이 신뢰도 낮은 순으로 쌓임. 인기 장소부터 확인
- 사진 보강: 장소별 상세 사진 `python -m pipeline.run import-tourapi --spot <id> --content-id <contentid>`
- 같은 명령을 다시 돌려도 이미 있는 장소는 건너뛴다 (contentid 기준)

## 5. 성능
장소가 늘면서 채점이 느려지는 문제를 006 마이그레이션으로 고쳤다 (600곳 기준 12.9초 → 35ms).
수만 곳 규모가 되면 `api/README.md` 5절의 사전 계산 테이블로 확장.
