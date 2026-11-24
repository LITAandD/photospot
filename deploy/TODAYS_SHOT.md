# 오늘의 한 컷 · 광화문·정동 시범

공개 서울 둘러보기 → `/today-shot`. 프로필·로그인·GPS 없이 한국시간 오늘을 기본으로 날짜와 동행·사진 목적·도착 시각을 선택한다. 선택하지 않아도 조회한다. 공유는 컷 ID와 날짜·조건을 그대로 보존하며, 임의 중심점으로 길찾기를 만들지 않는다. 기존 정합도·대표사진·장소 순위에는 연결하지 않는다.

## 공개 가능한 컷과 준비 상태

2026-11-24 기준 기존 활성 카탈로그 10,022곳 중 광화문·정동 10곳·20컷을 후보로 연결했다. **현장 검증 완료 0컷, 실제 추천 가능 0컷, 현장 확인 대기 20컷**이다. 장소 소개·관람안내를 확인한 것과 촬영 핀/이용 조건 검증은 다르다. 아래 컷 제목은 답사 계획이며 현재 촬영 가능한 위치라는 뜻이 아니다. 경복궁·덕수궁 시간표를 새 코드에서 추정하여 활성화하지 않는다.

데이터: `pipeline/data/shot_guides.json`. 모든 후보의 `pin`, `framing`, `field_review`, `place_schedule`, `access`, `photography`는 미확정으로 남겨 두었다. 공개 추천에서는 제외한다. 사진 수집·대표사진 변경·기존 운영시간 갱신은 하지 않았다.

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

길찾기는 [Google Maps URLs](https://developers.google.com/maps/documentation/urls/get-started#directions)의 보행 목적지 좌표로 생성한다. 장소명·중심점·현위치를 서버로 보내지 않는다. 지도가 구역 입구에서 종료하거나 통제 구역을 안내할 수 있어 실제 마지막 진입 경로는 별도 현장 확인 대상이다.

## 검토용 미리보기

일반 `/today-shot`은 현재 확인 대기 안내를 보여준다. Vercel **Preview** 또는 로컬 `APP_ENV=test`에서만 ‘검토용 시나리오 보기’를 제공한다. `review=open|weekly_closed|cutoff|temporary_closed|unknown|no_alternative`는 `api/shot_review.py`의 합성 데이터를 사용한다. `VERCEL_ENV=production`에서는 쿼리로 이 기능을 켤 수 없다(404).

검토 링크 예시: `/today-shot?city=seoul&date=2026-11-24&review=open&cut=test-cut-a&time=10%3A00`. 페이지·카드에 합성 테스트임을 표시한다. 길찾기 버튼은 연결을 시뮬레이션하며 실제 지도를 열지 않는다. 예시의 좌표·운영시간·검증일을 현장 안내로 사용해서는 안 된다. 검색 색인은 `X-Robots-Tag: noindex,nofollow`로 막고 사이트맵에는 추가하지 않는다.

## 통계와 개인정보

기존 선택 동의·철회·세션·테스트 트래픽 분류·90일 보관을 재사용한다. `shot_directions`, `shot_alternative`, `shot_completed`에 컷 ID와 결과만 보낸다. 세션/UTM 등 기존 공통 봉투는 유지한다. 서버는 이 세 이벤트의 추가 속성(좌표·사진·프로필 등)을 거절한다. 합성 검토 예시에서는 세 이벤트를 전송하지 않는다. 미동의·철회 후 전송 없음은 단위 검사로 확인한다. 저장 실패는 기존 503 및 `analytics_event_not_stored` 로그로 확인한다.

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
- 처음 방문한 별도 시험자가 안내만 보고 핀을 찾았는지, 구도를 재현했는지, 실패·수정 내용. **좌표가 지도 중심점인 경우 승인 불가.**
- 공식 장소 운영일·마감, 컷별 출입·촬영 규칙, 일시 통제·예약·개방 예외, 확인한 날짜 범위·출처·재확인일.
- 사진 촬영자·사용 허락·제3자 권리 또는 컷에 맞춘 자체 도식. 본 기능이 사용자 사진을 자동 수집하지는 않는다.
- 빛 안내가 있으면 실제 촬영 시각·방향·계절·차폐 조건의 관찰 근거. 미확인 시 비워 둔다.

현장 초행자 테스트, iPhone Safari·Android Chrome 실기기, 실제 보행 길찾기 도착 지점은 **미실행**이다. 검토 PR은 이 사항을 해결했다고 선언하지 않으며 운영 활성화는 미리보기 검토 후 별도 결정한다.

## 재현 검사

`python -m pytest tests/test_shot_guides.py -q`, 앱 타입·단위 검사, 웹 export 후 `APP_ENV=test python -m uvicorn deploy.vercel.index:app --port 8320`, `python app/e2e/today_shot_smoke.py`를 실행한다. E2E는 360/390/1280px에서 공개 진입·6상태·마감 전후·선택 미입력·대안·공유 새 창·통계 미전송을 검사한다. 기존 `public_detail_mobile.py`는 별도로 상세·대표사진·공유·맞춤 전환 회귀를 확인한다. 화면 캡처는 CI `today-shot-ui` artifact, 실행 결과·미리보기 URL은 PR 본문에 남긴다.
