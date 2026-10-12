# 실제 장소 데이터와 재현 검사

기준: 2026-10-12. 현재 기본 추천은 `catalog`이며 웹과 인증 API가 같은 SQLite 카탈로그를 읽습니다. PostgreSQL은 계정 데이터를 보관하고, `RECOMMENDATION_BACKEND=scenes`는 기존 장면 분석 경로를 선택합니다.

## 데이터 범위와 근거

배포 스냅샷은 `catalog/places.sqlite3`입니다. 최신 테이블별 행 수·수집일·스키마 버전·SHA-256은 [places.manifest.json](catalog/places.manifest.json)을 기준으로 봅니다. DB에 저장된 사진 수는 공개 표시가 허용된 사진 수와 다릅니다. 비활성 장소, 다른 지점 사진, 미확인 이용 조건은 API에서 제외합니다. 장소 수나 과거 수집 성공률이 현재 영업·촬영 허용 여부를 보증하지 않습니다.

- OSM 지도: [OpenStreetMap contributors / ODbL](https://www.openstreetmap.org/copyright). 이름·좌표·출처 ID로 장소를 관리합니다.
- 사진: Commons의 개별 파일 출처·작가·이용 조건, 검수된 허용 사진을 연결합니다. 변경 금지 사진은 원본 비율로 표시합니다.
- 공식 브랜드 사진: `ALLOW_OFFICIAL_BRAND_PHOTOS=0`이 기본입니다. 사이트에 공개되어 있다는 이유만으로 재사용 허락을 인정하지 않습니다.
- 네이버·Instagram 설명: 장소 식별과 원문 출처가 일치하는 검수 자료만 사용합니다. 공개 리뷰·게시물 수를 실제 방문객 수로 바꾸어 해석하지 않습니다.
- MBTI E/I는 2025년 방문객 통계가 있는 장소끼리 비교합니다. 미확인 장소는 미평가입니다. S/N은 설명 문구와 부정어 처리, T/F는 건축적·자연적 특징, J/P는 확인된 계획 필요성·자유 방문 근거를 사용합니다.
- 정합도는 전체 지표 배점 기준이며, 미평가 항목을 만점으로 환산하지 않습니다. 전체 점수를 먼저 정렬하고 평가 범위 등을 동점 기준으로 사용합니다. 키 170cm 기준은 적용하지 않습니다.

## 운영시간

공식 시간표는 현재 추천 대상 스타벅스 더북한산·파미에파크R·서울웨이브아트센터 3곳에 적용됩니다. 2026-10-12 확인한 게시 기간은 10/12~18입니다. 이전에 추천에서 제외된 343곳의 시간표는 갱신 자료에서도 제거했습니다. 실패한 활성 지점의 기록은 보존하되 게시 기간이 지나면 실제 시간 대신 확인 안내를 표시합니다.

네이버 확인 시간, OSM의 요일·시즌·휴관 규칙도 출처별로 처리합니다. 야외라는 이유로 24시간 운영을 추정하지 않으며 복잡한 OSM 조건은 원문 안내를 보존합니다. 촬영일이 공식 게시 기간 밖이면 같은 요일 시간으로 연장하지 않습니다.

[데이터 갱신 workflow](.github/workflows/data-refresh.yml)는 매주 월요일 KST에 공식 시간을 수집해 PR을 만듭니다. 해당 PR의 병합·배포가 완료되어야 웹에 적용됩니다. HTTP 403/429에는 재시도하거나 다른 주소로 우회하지 않고 실패를 보고합니다.

## 실행과 갱신

[README](README.md)의 가상환경 설정 후 다음 명령은 Windows/macOS/Linux에서 같습니다.

```sh
npm --prefix app run demo -- --port 8081
python -m scripts.check_data_freshness --json
python -m scripts.audit_place_hours
```

수집 작업은 실행 중인 앱과 분리된 작업용 DB에서 진행합니다. `PLACE_CATALOG_DB`를 작업용 경로로 지정하세요. PowerShell은 `$env:PLACE_CATALOG_DB='작업용 경로'`, macOS/Linux는 `export PLACE_CATALOG_DB='작업용 경로'`를 사용합니다. 배포 스냅샷을 복사해 갱신하거나 다음 명령으로 허용된 출처를 수집합니다.

```sh
python -m pipeline.place_catalog --regions seoul,busan,jeju,gangneung
python -m pipeline.cafe_photos
python -m pipeline.catalog_photos --scan --link
python -m pipeline.cafe_popularity --import-json pipeline/data/cafe_popularity.json
python -m pipeline.official_place_hours
python -m scripts.check_data_freshness --source official_place_hours --fail-within 0
python -m scripts.export_catalog
```

권한 있는 API 키가 필요한 수집은 서버 환경에서만 설정합니다. 키·프로필·생년월일은 공개 카탈로그에 포함하지 않습니다. 앱 조회 중 외부 사이트 수집은 실행하지 않습니다. 갱신 후 API를 다시 배포해 파일과 캐시를 함께 반영합니다.

`export_catalog`는 허용된 공개 테이블만 새 파일에 정렬해서 내보내고 manifest를 생성합니다. 신규 export 스키마 버전은 1이며 기존 배포 파일의 버전 0도 manifest에 명시합니다. JSON 검수 자료만 바뀌었다면 `python -m scripts.export_catalog --manifest-only`로 DB를 재작성하지 않고 출처 해시를 갱신합니다. CI는 스냅샷과 manifest의 일치를 확인합니다.

## 사진과 포즈

대표 사진은 `photo_framing_reviews.json`의 URL·원본 페이지가 정확히 일치하는 검수 결과를 우선 적용합니다. 그 외에는 제목·짧은 설명·실내 사진 메타데이터로 보수적으로 선택합니다. 근경 여부를 확인할 수 없으면 기존 사진 순서를 유지합니다. 전체 장소의 사진 픽셀을 자동 분석했다는 뜻은 아닙니다.

`pose_reference_reviews.json`에 검수된 인물의 사진 높이 비율과 발 위치를 보관합니다. 실제 키·신원은 저장하지 않습니다. 상세 화면에서 머리와 발을 선택하거나 작게/크게 조절할 수 있습니다. 미검수 사진은 기본 비율이며 자동 인물 검출로 표시하지 않습니다.

## 검증 자료

[출시 상태](RELEASE_STATUS.md)의 공통 명령과 [CI](https://github.com/LITAandD/photospot/actions/workflows/ci.yml)를 사용합니다. CI 웹 검사는 격리된 `tests/fixtures/` 데이터로 실행하며 사용자 DB나 브라우저 프로필을 바꾸지 않습니다. 로컬 `artifacts/`는 실행 시 생성되고 Git에 포함되지 않습니다. 테스트 수와 현재 보안 경고는 [검토 결과](REVIEW_2026-10-12.md)에서 관리합니다.
