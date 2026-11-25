# 오늘의 한 컷 · 광화문·정동 시범

공개 서울 둘러보기 → `/today-shot`. 프로필·로그인·GPS 없이 한국시간 오늘을 기본으로 날짜와 동행·사진 목적·도착 시각을 선택한다. 선택하지 않아도 조회한다. 공유는 컷 ID와 날짜·조건을 그대로 보존하며, 임의 중심점으로 길찾기를 만들지 않는다. 기존 정합도·대표사진·장소 순위에는 연결하지 않는다.

## 공개 가능한 컷과 준비 상태

현재 상태·통과 수·스크린샷은 PR과 `python -m api.shot_guides check` 출력에 기록한다. 후보 제목은 답사 계획이며 촬영 가능 위치를 뜻하지 않는다. 후보 선정 참고 `source_review`는 운영 판정에 쓰지 않으며 `place_schedule.source`로 복사하지 않는다. 실제 핀·권리·접근·초행자 재현 근거가 없는 후보는 공개 추천에서 제외한다.

| 기존 장소 ID | 장소 · 컷 ID | 답사할 구도 후보 2개 | 확인한 공식 안내 · 2026-11-24 | 남은 확인 |
|---|---|---|---|---|
| 3e425403-dffd-54ed-8d4c-eecb2223c763 | 경복궁 · gbg-01/02 | 근정전 정면 / 회랑 인물 | [관람코스](https://royal.khs.go.kr/ROYAL/contents/R701000000.do?schGroupCode=gbg) | 정지 가능한 핀, 화요일·특별 개방, 회랑 접근·촬영 규칙 |
| 3fe8ed45-05ab-5fad-8e2c-7f659665256c | 광화문광장 · square-01/02 | 광화문 방향 / 광장 인물 | [광장 공식](https://gwanghwamun.seoul.go.kr/ghm/main.do) | 행사 점유·보행로·시야·구역별 촬영 조건 |
| 7f590a31-602f-5277-8534-ea1f7d86bc7c | 덕수궁 · deoksu-01/02 | 중화전 정면 / 돌담 배경 | [궁능 관람시간](https://royal.khs.go.kr/ROYAL/contents/R702000000.do) | 정확한 촬영 구역, 월요일·특별 개방·입장마감 |
| a133eea8-fe35-50b1-8402-e975f2bee89d | 중명전 · jungmyeong-01/02 | 외관 / 진입 공간 인물 | [국가유산포털](https://www.heritage.go.kr/heri/html/HtmlPage.do?pageNo=2_3_2_0&pg=%2Fpalaces%2Fwatch_info%2FpalacesDeokJmjGuide.jsp) | 본궁과 분리된 출입·야외 촬영 범위 |
| c8d386f3-f380-5a32-9191-429b8e9d7320 | 서울시립미술관 서소문본관 · sema-01/02 | 외벽 / 야외 진입부 | [서소문본관](https://sema.seoul.go.kr/kr/visit/seosomun) | 외부 공간 이용·촬영, 전시 촬영 허가와 분리 |
| 720135d2-a279-582c-88b2-fe658c2682ed | 서울역사박물관 · seoul-history-01/02 | 외관 / 광장 인물 | [시설 안내](https://museum.seoul.go.kr/www/intro/annexIntro/annexInfo.jsp?sso=ok) | 야외 전시물 권리·정지 구역·동선 |
| 603a044c-3b26-50b5-8ac9-dc313ed1e44c | 경희궁 · gyeonghui-01/02 | 정면 건축 / 마당 인물 | [관람안내](https://museum.seoul.go.kr/www/support/ghp/supportBranchGHPShow.jsp?sso=ok) | 부분 통제·촬영·실제 진입 동선 |
| 2e36f567-36c0-542c-924a-11c5cd2d8f0c | 국립고궁박물관 · palace-museum-01/02 | 외관 / 접근 공간 | [박물관 공식](https://www.gogung.go.kr/gogung/main/main.do) | 시설 주변 접근·지점별 촬영 조건 |
| 64dcd142-8201-52d2-9cbb-64ec642873c7 | 대한민국역사박물관 · much-01/02 | 정면 / 지상 진입부 | [관람·촬영 유의사항](https://www.much.go.kr/MUCH/contents/M01020100000.do) | 지상 핀 확인. 옥상 조감뷰 제외 |
| 2dab768d-79b3-5970-9d9e-53eb5579346d | 국립정동극장 · theatre-01/02 | 외관 / 야외마당 | [시설 소개](https://www.jeongdong.or.kr/portal/main/contents.do?menuNo=200011) | 비공연일 마당 출입·촬영·공사 여부 |

덕수궁과 경희궁은 카탈로그의 동명이인·중복 노드 중 주소가 확인된 시설 ID 하나만 사용했다. 장소 중심 좌표는 촬영 핀으로 복사하지 않았다. 기존 사진 URL과 SQLite SHA-256 `12bd640466c8104ab2e331785f000526964c6c71ea1ce859b1bb0806f8e60996`를 보존한다. 매니페스트는 신규 후보 JSON 해시만 추가한다.

## 컷 승인 및 제외 규칙

`api/shot_guides.py`의 모델이 출처·확인일·유효기한, 구체적 핀·진북 방위·기준물·진입 안내, 프레이밍, 태그, 도식/사진 권리, 현장 검증을 각각 보관한다. 장소 운영표(`place_schedule`)와 컷 접근표(`access`)는 별도다. 요일표는 확인된 빈 배열이면 휴무, 키가 없으면 미확인이다. 날짜별 예외표가 정기표보다 우선하며 임시 통제 이유를 표시한다. 자정 넘김 시간표는 이번 스키마에서 받지 않는다.

1. 검증된 휴무·마감·접근 통제를 먼저 제외한다. 입장마감 시각부터는 신규 입장을 추천하지 않는다. 컷별 촬영 금지는 `photography_allowed=false`로 제외한다.
2. 자료의 확인일이 미래이거나 유효기간 밖이면 제외한다. 오늘과 선택 방문일 모두 근거 유효기간 안이어야 한다. 신규 예외·행사 공지가 없는지 확인한 기간까지만 유효기한을 설정한다. 운영·입장마감 미확인도 제외한다.
3. `verified` 상태만으로 공개되지 않는다. 실제 핀과 현장 초행자 재현·안전 확인, 출처와 컷별 촬영 허용, 구도와 사용권도 모두 있어야 한다. 사진은 HTTPS·정확한 컷 검수·기존 라이선스 게이트를 통과해야 하며 변경금지 사진은 원비율로 표시한다. 자체 도식은 촬영 사진이나 지도로 표시하지 않는다.
4. 남은 컷 중 사진 목적을 맞추고 동행 태그 일치 우선, 동점은 컷 ID로 고정한다. 프로필 점수·연간 방문객·혼잡·날씨를 사용하지 않는다.
5. 공유로 선택된 컷이 제외되면 같은 목적의 검증된 대체 컷 **최대 1개**만 보여준다. 없는 경우 ‘이 조건에서 확인된 컷이 없어요’로 끝낸다. 선택한 시간 미입력은 검색을 막지 않지만 ‘촬영 가능’이라고 단정하지 않는다.
6. 좋은 빛 안내는 별도의 유효한 현장 근거가 있을 때만 표시한다. 일반적인 일몰 계산은 넣지 않았다.

길찾기는 검증된 컷 핀을 목적지로 하는 카카오맵 웹을 기본으로 한다. 네이버 지도 앱은 모바일 보조이며 Google은 위치 보기다. 이용자 현위치는 수집하지 않는다. 실제 마지막 진입 경로와 기기별 도착 지점은 별도 현장 확인 대상이다.

## 검토용 미리보기

일반 `/today-shot`은 현재 확인 대기 안내를 보여준다. Vercel **Preview** 또는 로컬 `APP_ENV=test`에서만 ‘검토용 시나리오 보기’를 제공한다. `review=open|weekly_closed|cutoff|temporary_closed|unknown|no_alternative`는 `api/shot_review.py`의 합성 데이터를 사용한다. `VERCEL_ENV=production`에서는 쿼리로 이 기능을 켤 수 없다(404).

검토 링크는 `/today-shot`의 시나리오 버튼으로 연다. 버튼은 KST 내일 날짜·선택 컷·시간을 주소에 보존한다. 페이지·카드에 합성 테스트임을 표시한다. 길찾기 버튼은 연결을 시뮬레이션하며 실제 지도를 열지 않는다. 예시의 좌표·운영시간·검증일을 현장 안내로 사용해서는 안 된다. 검색 색인은 `X-Robots-Tag: noindex,nofollow`로 막고 사이트맵에는 추가하지 않는다.

## 통계와 개인정보

기존 철회·세션·테스트 트래픽 분류·90일 보관을 재사용하되 오늘의 한 컷 통계는 별도로 추가 허용해야 한다. 조회 결과·컷 ID·행동 결과와 지도 제공자, 대체 선택 시 원래 컷 ID만 보낸다. 세션/UTM 등 기존 공통 봉투는 유지한다. 서버는 좌표·사진·프로필·조회 조건과 합성 컷 ID를 거절한다. 합성 검토 예시에서는 추가 동의가 있어도 전송하지 않는다. 미동의·철회 후 전송 없음은 단위 검사로 확인한다. 저장 실패는 기존 503 및 `analytics_event_not_stored` 로그로 확인한다.

```sql
SELECT event, props->>'cut_id' AS cut_id, count(*) AS actions
FROM analytics_events
WHERE props->>'schema_version' = '2' AND props->>'traffic' = 'production'
  AND event IN ('shot_directions','shot_alternative','shot_completed')
  AND created_at >= now() - interval '7 days'
GROUP BY event, props->>'cut_id';
```

완료 버튼은 자기보고 동작 수이며 실제 촬영·고유 이용자 수나 전환율로 해석하지 않는다. 미리보기에는 운영 DB를 연결하지 않으며 실제 운영 통계 행을 쓰지 않는다.

## 현장 검수 기록 양식 · 활성화 전 필수

컷마다 다음을 기록한 뒤 JSON·미리보기·동일 입력 회귀 테스트를 리뷰한다. 원격 개발로 현장 확인을 대신하지 않는다.

- 장소 ID / 컷 ID / 답사일·시각(KST) / 검수자와 근거 문서 참조.
- 촬영자가 서는 정확한 좌표와 측정법·오차, 기준물과 안전한 정지 영역, 실제 진입 경로·계단·차도·출입 통제.
- 진북 방위, 바라볼 기준물, 휴대폰 배율·가로세로·눈높이·프레이밍. 촬영자 및 동행인의 구역 점유·방해 여부.
- 처음 방문한 별도 시험자가 안내만 보고 핀을 찾았는지, 구도를 재현했는지, 실패·수정 내용. **지도 중심점 복사로 핀을 만들면 승인 불가.** 독립 현장 측정값이 카탈로그 좌표와 3m 이내라면 우연한 중첩 여부를 별도 검수하고 기록해야 한다.
- 공식 장소 운영일·마감, 컷별 출입·촬영 규칙, 일시 통제·예약·개방 예외, 확인한 날짜 범위·출처·재확인일.
- 사진 촬영자·사용 허락·제3자 권리 또는 컷에 맞춘 자체 도식. 본 기능이 사용자 사진을 자동 수집하지는 않는다.
- 빛 안내가 있으면 실제 촬영 시각·방향·계절·차폐 조건의 관찰 근거. 미확인 시 비워 둔다.

현장 초행자 테스트, iPhone Safari·Android Chrome 실기기, 실제 보행 길찾기 도착 지점은 **미실행**이다. 검토 PR은 이 사항을 해결했다고 선언하지 않으며 운영 활성화는 미리보기 검토 후 별도 결정한다.

## 재현 검사

`python -m pytest tests/test_shot_guides.py -q`, 앱 타입·단위 검사, 웹 export 후 `APP_ENV=test python -m uvicorn deploy.vercel.index:app --port 8320`, `python app/e2e/today_shot_smoke.py`를 실행한다. E2E는 360/390/1280px에서 공개 진입·6상태·마감 전후·선택 미입력·대안·공유 새 창·통계 미전송을 검사한다. 기존 `public_detail_mobile.py`는 별도로 상세·대표사진·공유·맞춤 전환 회귀를 확인한다. 화면 캡처는 CI `today-shot-ui` artifact, 실행 결과·미리보기 URL은 PR 본문에 남긴다.

## 현장 기록 → 검수 데이터

1. `Place.place_id`는 활성 카탈로그 지점을 선택한다. 후보 제목·공식 소개 페이지는 검수 완료 증거가 아니다.
2. `Cut.id/status/pending`으로 상태를 관리한다. `verified`에는 미해결 pending을 남길 수 없다.
3. `Pin.method/lat/lng/accuracy_m`에 독립 현장 측정을 기록한다. field 방식은 공개 URL 대신 `FieldReview.record_ref`를 사용한다. 내부 기록·검수자 신원은 공개 응답에 넣지 않는다. 공식 촬영 표식 방식만 공개 `Pin.evidence`가 필요하다.
4. `FieldReview.checked_at/valid_until/first_time_tester_found_pin/framing_reproduced/safe_standing_area/independent_measurement`를 실제 검수 결과로 작성한다. 3m 안에서 카탈로그 좌표와 겹치면 독립 측정과 `catalog_overlap_reviewed` 재검수가 필요하다. 같은 좌표라는 사실만으로 측정이 허위라고 판단하지 않는다. 기본 500m 이상 이격은 보류하며 넓은 시설 예외는 `Place.max_pin_distance_m/pin_distance_note`에 근거를 남긴다.
5. 장소 운영은 `Place.place_schedule`, 컷 접근은 `Cut.access`, 촬영 제한은 `Cut.photography/photography_allowed/restrictions`다. 독립 접근이 확인된 야외 컷만 `area=public_outdoor`로 지정한다. 실내 표를 24시간으로 바꾸어 우회하지 않는다.
6. Schedule의 `weekdays` 키는 **0=월요일…6=일요일**이다. 빈 목록은 확인된 휴무, 키 누락은 미확인이다. `exceptions`가 우선하며 `exception_notes`는 대응하는 예외가 있을 때만 쓴다. `source.checked_at/valid_until`은 31일 이내이며, `applies_from/applies_until`은 실제 동일 시간표 적용 기간으로 제한한다. **계절 시간표 경계를 넘기지 않는다.** 계절별 다중 기간은 후속 확장 전까지 한 적용 기간만 검수한다.
7. 24시간은 `Window(all_day=true, opens="00:00", closes="00:00")`와 `admission_required=false`로 명시한다. 23:59 폐쇄는 24시간으로 추정하지 않는다.
8. JSON 수정 → `python -m api.shot_guides check --path <사본> --date YYYY-MM-DD` → `python -m scripts.export_catalog --manifest-only` → 관련 pytest → 미리보기 → 현장 확인 → 별도 운영 승인 순서다. CLI는 값 대신 오류 위치·종류만 출력하며, 후보 행은 대기 상태여도 종료 0이다. verified 근거 미비는 종료 1이다.

서울 둘러보기는 `/preview/shots?visit_date=YYYY-MM-DD&view=entry`로 날짜·진입 가능 여부·실제/검토 모드만 받는다. 전체 결과와 같은 근거·휴무·핀 검증을 적용하며 카드·사진·출처 직렬화는 생략한다. 기본 조회는 전체 응답을 유지하고 캐시 정책은 바꾸지 않는다. 조건 변경·재시도·화면 종료 시 이전 클라이언트 조회를 중단하되 이미 서버에서 실행 중인 계산이 취소됨을 보장하지 않는다.

진입 카드는 서로 다른 장소 3곳 이상·인물과 건축 목적 각각 1컷 이상일 때만 표시한다. 합성 검토 데이터는 진입 준비 판정에서 제외한다. 기존 통계 선택과 오늘의 한 컷 통계 추가 허용을 모두 받아야 새 이벤트를 보낸다. 과거 공유 날짜는 자동 변경하지 않는다.


## 길찾기·당일 안내·일일 점검

- 기본 길찾기는 카카오맵 웹의 촬영 핀 목적지다. 네이버 앱 경로는 보조 수단이며 앱 설치·실기기 도착 지점을 별도로 확인한다. Google 링크는 위치 보기만 제공하며 국내 도보 경로 지원을 전제하지 않는다.
- URL 형식 확인: [카카오 공식 지도 URL](https://apis.map.kakao.com/web/guide/#routeurl), [네이버 공식 앱 URL Scheme](https://guide.ncloud-docs.com/docs/maps-url-scheme), [Google Maps URL](https://developers.google.com/maps/documentation/urls/get-started) (2026-11-24). URL 생성 테스트는 실제 접근 경로 검증을 대체하지 않는다.
- 오늘은 한국시간의 현재 분보다 과거인 도착시각과 남은 입장창이 없는 컷을 제외한다. 미래 날짜는 선택한 시각만 비교한다. 검토 시나리오는 한국시간 내일을 사용한다.
- `python -m scripts.check_data_freshness --source shot_guides --fail-within 7`로 검증 컷의 장소·접근·촬영·핀·현장 근거 중 가장 빠른 재확인 기한을 점검한다. 빛 관찰만 만료되면 빛 문구만 숨긴다. 비활성 장소나 유효하지 않은 근거는 즉시 재검수 대상으로 표시한다. 후보는 만료 집계에 포함하지 않는다.
- `goal_counts`는 그 날짜·시간에 근거를 통과한 컷 수이며 목적 필터 적용 전 값이다. 빈 결과의 `excluded.code`는 대기·제한·휴무·마감·유형 불일치를 구분한다. 후보 제목은 답사 계획이며 촬영 가능한 위치라는 뜻이 아니다.


## 선택 통계 확인

일반 통계 동의와 별도로 오늘의 한 컷 추가 허용이 있어야 `shot_view`, 공유, 길찾기, 대체 컷, 완료 응답을 보낸다. 기존 이용자의 선택은 자동 확장하지 않는다. 검토 모드는 추가 동의가 있어도 전송하지 않는다. 동행·목적·방문일·시각·좌표·사진은 포함하지 않는다. 대체 컷은 `alternative_available`(대안 제시)로 집계하며 실제 교체·촬영 성공으로 해석하지 않는다.

```sql
SELECT count(*) FILTER (WHERE event='shot_view') AS views,
       count(DISTINCT session_id) FILTER (WHERE event='shot_view') AS view_sessions,
       count(*) FILTER (WHERE event='shot_view' AND props->>'result'='empty')::float
         / NULLIF(count(*) FILTER (WHERE event='shot_view'),0) AS empty_view_ratio,
       count(DISTINCT session_id) FILTER (WHERE event='shot_directions') AS direction_sessions,
       count(*) FILTER (WHERE event IN ('shot_directions','shot_alternative','shot_completed')) AS actions,
       count(DISTINCT session_id) FILTER (WHERE event IN ('shot_directions','shot_alternative','shot_completed')) AS action_sessions
FROM analytics_events WHERE props->>'traffic'='production'
  AND created_at >= CURRENT_TIMESTAMP - INTERVAL '30 days';
```

기존 actions 의미는 유지한다. 위 열은 조회·클릭 집계이지 순서가 입증된 전환율이나 현장 방문 증명이 아니다. 같은 탭의 완료 표시 중복 방지는 서버의 방문 증명과 구별한다. 저장 실패는 기존 `analytics_store_failed` 로그와 503 응답으로 확인한다.


## 다음 워크플로우 · 운영 활성화 전

1. **코드 검토:** 진입·동의 게이트 → 데이터 모델·검수 CLI → 안내 정확도·만료 점검 → 선택 통계 → 모바일 화면 순서의 연결 Draft PR을 검토한다. 각 PR의 기준 브랜치를 먼저 병합한 뒤 다음 PR 기준을 main으로 바꾸고 CI를 재확인한다. 이 절차 문서 자체는 병합·배포 승인이 아니다.
2. **현장 계획 확정:** 운영 담당자·검수자·처음 방문하는 별도 시험자, 비공개 현장 기록 보관 위치·보유기간·동의를 정한다. 공개 JSON에는 `record_ref`만 남긴다. 기존 방문자 사진 접수 동의를 현장 검수 기록 동의로 재사용하지 않는다.
3. **첫 답사:** 광화문광장·덕수궁 돌담길 등 공공 야외 컷을 우선 후보로 검토하되 야외라는 이유만으로 무제한 이용을 추정하지 않는다. 서로 다른 장소 3곳과 인물·건축 각 1컷 조건을 충족하려면 추가 장소도 검수해야 한다.
4. **근거 입력:** 날짜·시간표 실제 적용 기간·예외·촬영 허용·핀 독립 측정/오차·출입 동선·안전·도식 구성(`visual.composition`) 또는 사진 권리를 기록한다. 계절 시간표 경계를 넘기지 않고 31일 이하로 재확인한다. `check` → 매니페스트만 재생성 → 관련 테스트 → 별도 데이터 PR으로 진행한다.
5. **실기기·현장 확인:** iPhone Safari·Android Chrome에서 비로그인 공유 재접속, 같은 컷·날짜, 카카오/네이버 촬영 핀 목적지와 실제 접근 경로를 확인한다. 보조기기 VoiceOver·TalkBack과 앱 미설치 상황을 별도 확인한다. 자동 화면 검사는 이 단계를 대체하지 않는다.
6. **최종 승인:** CI 전체, 미리보기, 첫 화면 진입 조건, 권리·유효기한, 개인정보 추가 선택·철회, 테스트 트래픽 분리, 기존 공개 상세·사진·공유 회귀, 운영 도메인 후보와 롤백 대상을 확인한 후 별도 운영 승인을 받는다. 실제 검수 컷이 없으면 서울 진입 카드는 숨김 상태를 유지한다.

보류: 계절별 periods 확장, 일별 동점 무작위 순환, 조회 조건의 통계 수집, 전국 좌표 범위 확대. 최초 기본값은 3개 장소+인물/건축, 마감 후 제외, 최소 조회 결과 통계다. 실제 현장 기록과 운영 활성화는 별도 검토한다. 화면 캡처와 실행 결과는 CI artifact/PR 본문에 두며 이 문서는 절차만 유지한다.
