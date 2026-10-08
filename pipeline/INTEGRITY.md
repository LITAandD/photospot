# 사진 → 점수 정합성 원칙

첫 세 절은 PostGIS 장면 엔진 기준이다. 공개 웹 카탈로그는 아래 웹 카탈로그 절과 [현재 정합도 규칙](PROFILE_FIT.md)을 따른다.

추천 점수는 **사진에서 분석한 장면** 또는 **사람이 확정한 장면**에서만 나온다. 그 외 정보는 장소를 목록에 올리고 사진을 모으기 위한 보조일 뿐 점수에 들어가지 않는다.

## 근거(evidence) 세 단계
| evidence | 어떻게 생기나 | 채점 |
|---|---|---|
| `category` | TourAPI 분류 코드, 네이버 검색 테마로 붙인 초기 태그 | **안 함** (앱에 "사진 분석 전"으로 표시, 검수 대기열) |
| `photos` | 파이프라인이 사진(직접 촬영·공공·사장님·사용자·인스타 분석)을 집계 | 사진 **3장 이상**, 신뢰도 **0.6 이상**일 때만 (`score_settings.min_photos`, `min_confidence`) |
| `human` | 사람이 입력·검수 확정 (`/v1/admin/scenes/{id}`) | 항상 |

사진이 더 모이면 `photos` 장면의 장수·신뢰도가 올라가 자연히 채점에 들어온다. 검수는 `category`·불안정한 `photos` 장면을 `human`으로 확정하는 일이다.

## 재현성
- 같은 사진 집합이면 순서·재실행과 무관하게 같은 태그가 나온다 (테스트로 고정).
- 사진별 분석 결과(`photos.labels`, `external_media.labels`)를 저장하므로 장면 태그는 언제든 다시 집계할 수 있다.
- 기준값(`config.py`)이나 규칙을 바꾸면 저장된 태그와 어긋난다. `python -m pipeline.run integrity`가 이를 잡아낸다:
  - 근거별 장면 수와 채점 가능 수
  - 재집계 시 태그가 달라지는 장면 (0이어야 정상. 있으면 `analyze --reanalyze` 로 재분석)
  - 채점 장면 중 태그 신뢰도 0.5 미만인 것 (사진 추가 또는 검수 대상)
  - 사진 근거지만 기준 미달인 장면 (사진 몇 장이 더 필요한지)
  종료 코드가 0이 아니면 CI에서 실패하도록 붙여둘 수 있다.

## 앞으로 붙일 것 (점수 근거를 늘리는 두 입구)
- **사용자 후기 + 사진**: 이미 `POST /v1/photos`·후기 API가 있다. 사용자 사진은 동의 아래 `photos` 근거가 된다.
- **사장님 등록·홍보**: `place_owners`, `owner_upload` 사진, `instagram_handle`. 사장님 사진은 가장 신뢰도 높은 근거이고 약관 부담이 없다. 등록 화면과 승인 흐름이 남은 작업.

## 웹 카탈로그의 카페 및 식당 선정 (2026-10-08)

웹 체험판의 SQLite 카탈로그는 `cafe` 검색 그룹에 `cafe`, `bakery`, `restaurant`를 포함한다. 그룹 키는 이전 저장 링크와 호환되며 화면 이름은 ‘카페 및 식당’이다. 베이커리·식당에도 기존 사진 검증과 출처가 있는 리뷰 집계 규칙을 적용한다.

`data/dining_curation.json`은 16개 공간의 정확한 OSM 식별자·좌표·지점명·선정 이유·출처를 담는다. 서울 6곳, 부산 6곳, 강릉 3곳, 제주 1곳이다. 원본 지점 사실은 `data/dining_osm.json`에 최소한의 공개 태그만 저장했다. 관광공사·지역 취재·공개 방문 사진을 참고한 편집 선정이며 **인스타그램 게시물 수나 최근 방문객 수 순위가 아니다**. 수치가 없는 소개 자료를 인기 점수·혼잡도·정합도에 더하지 않는다. 선정 이유와 사진을 볼 수 있는 출처는 장소 상세에 표시한다. 사진 자체를 확인·분석하지 않은 속성은 미평가로 남는다.

스타벅스는 더북한산·서울웨이브아트센터·파미에파크R 3곳만 선정했다. 나머지 441곳과 연결된 사진·분석·방문객·인기·지역 연결 행은 삭제했다. 이름(한/영)과 브랜드 태그를 검사해 다음 OSM 수집에서도 일반 지점을 제외한다. 다른 카페는 이 브랜드 제한을 받지 않는다.

적용 명령은 `python -m pipeline.dining_curation`이다. 전체 입력의 지점 일치를 먼저 검증하고 `storage/backups/before-dining-*.sqlite3`에 원본을 백업한 뒤 한 트랜잭션으로 삭제·보강한다. 이 변경에서 신규 10곳을 추가하고 기존 6곳을 보강했다. 각 지역의 `:dining` 연결은 일반 지역 새로고침으로 사라지지 않는다. 반복 실행은 장소를 중복 생성하지 않는다. 배포 전 `python -m scripts.export_catalog`로 공개 스냅샷을 갱신한다. 백업은 Git과 Vercel 업로드에 포함하지 않는다.

추천 순서는 평가 완료 항목 수 내림차순, 동률이면 정합도 내림차순이다. ‘사진 명소 선정’ 표시는 이 우선순위를 바꾸지 않는다.

웹 카탈로그의 종합 정합도는 **획득 배점 합계 / 전체 기본 배점 100 × 100**으로 계산한다(소수점 한 자리, 0~100점 범위). 평가된 항목만 분모로 삼지 않는다. 예를 들어 체형만 30점을 받고 나머지가 미평가라면 30/100점이다. 퍼스널컬러 40점·체형 30점·MBTI 30점이며, 키와 J/P는 배점에 포함하지 않는다. 프로필 미입력·근거 미확인 항목은 점수를 더하지 않지만 전체 배점에는 포함한다. 항목 상태와 기여 점수 `null`은 유지하여 미평가와 평가 결과 0점을 구별한다. 평가 완료 항목이 전혀 없으면 종합 점수도 `null`(산정 전)이다. 오행·일진 점수는 이 기본 배점과 합산하지 않는다.
## Public Instagram references (display only)

`data/instagram_places.json` records reviewed public post/reel permalinks and exact
OSM branch matches. Import with `python -m pipeline.catalog_instagram`, then export
with `python -m scripts.export_catalog`. Review the public post and its branch
before adding an entry; `checked_at` is the review date, not the photo date.
The importer validates all entries before atomically replacing the reviewed set;
removing an entry withdraws its reference on the next import/export/deployment.

The web client uses Instagram's official `embed.js` with an original-post link
that remains available when embeds fail. No downloaded photos, CDN URLs, captions,
engagement counts, access tokens or oEmbed response metadata enter the catalog.
References do not increase photo counts, photo-only eligibility, popularity,
evaluation coverage, or fit scores. Native clients open the original post.
Public posts can later become unavailable or disable embedding; recheck and
withdraw broken references through the manifest. Remaining unverified venues
keep their existing missing-photo state.

Official display reference: https://developers.facebook.com/documentation/instagram-platform/oembed

2026-10-08 추가 확인: 기존 선정 카페·베이커리·식당 16곳 모두에 공개 원본
게시물 17개를 연결했다(기존 5곳 6개에서 11곳 추가). 스타벅스 선정 3곳은
기존 공식 사진을 유지한다. 신규 연결은 게시물의 지점명·주소 또는 지점 공식
계정을 대조하고 실제 사진을 확인했다. 우물집 홍대/명동, 어니언 성수/안국,
모모스 온천장/영도, 런던베이글 안국/더현대서울을 각각 별도로 매칭했다.
여행 사이트에서 명동점으로 소개한 `CwWj7eMpKBw`는 원본에 홍대점 주소가
명시되어 있어 홍대에만 연결하고, 명동에는 공식 명동점 계정의
`C55Kt9OvEa8`을 사용한다. 이 완료 범위는 선정 16곳이며, 전체 4,412개
카페·식당의 사진 확인이 끝났다는 의미는 아니다.

## 네이버 공간 사진: 명시적 재사용 허용분만 표시 (2026-10-08)

`data/naver_photos.json`은 원문 하단의 CCL, 작성자, 정확한 OSM 지점,
원문 주소, 확인일, 사진별 육안 검수 내용을 기록한다. 검색의 ‘상업적 이용
가능’ 표시는 후보 선정에만 사용하며, 원문에서 현재 허용 조건을 확인해야 한다.
공개 네이버 지도·플레이스 사진이나 CCL이 없는 블로그 사진에는 허용을 추정하지 않는다.
비상업 전용 사진은 제외한다. 별도 사진 파일 복제 없이 확인한 원문 이미지 URL을 표시한다.

이번에 10곳에 대표 공간 사진 10장을 추가했다: 대림창고, 빌리프커피로스터스,
비아트 성수, 루프 성수, 따우전드 성수, 코랄라니, 테라로사 커피공장 강릉본점,
우물집 홍대점, 동화가든 강릉본점, 우진해장국. CC BY-ND 2.0 KR 7장과
CC BY-SA 2.0 KR 3장이다. ND 사진은 목록의 정사각 프레임에서도 원본 비율로
표시하며 크롭·스케치·사진 위 배지를 적용하지 않는다. SA 사진의 크롭·스케치
표시에도 동일 라이선스를 안내한다. 상세 화면에서 작성자, 원문, 라이선스,
원본 사진을 확인할 수 있다. 외부 URL이 삭제되거나 응답하지 않으면 기존 오류 상태를 표시한다.

`python -m pipeline.naver_photos`는 전체 검증 후 이 공급자의 검수 목록만
트랜잭션으로 교체한다. 다른 공급자의 사진을 보존하며 Commons 갱신도 이 목록을
삭제하지 않는다. 지점 이름/좌표/주소가 달라지면 재검수 전까지 숨긴다. 동화가든의
기존 OSM 주소 표기는 원문 도로명 주소와 달라, 원문 지도 좌표와의 거리(23m 이내),
입구 간판, 정확한 지점명을 대조하고 기존 주소 문자열과 검수 이유를 별도로 고정했다.
출처 철회는 manifest에서 삭제한 뒤 import/export/deploy한다.

바우카페 사천 본점과 DB의 연곡점, 테이큰커피 성수점과 DB의 다른 좌표를
같은 지점으로 취급하지 않았다. 피아크·우물집 명동 등 현재 원문 CCL을 확인하지
못한 후보와 마일스톤 성수의 비상업 전용 사진도 제외했다. 전체 4,412개
카페·식당의 확인을 마친 것은 아니며, 이번 추가분만 검수 완료 상태다.
사진 링크 추가는 사진에서 추론한 체형·색온도 점수나 방문객 수를 생성하지 않는다.


## MBTI 근거 개편 (2026-10-08)

2025년 확정 입장객 통계에서 정확한 통계 단위와 매칭한 36곳을 수록했다.
네이버 공간 리뷰·Instagram 공개 공간 설명 9곳을 별도 검토했다.
이 중 S/N 판정 문구가 확인된 곳은 런던베이글 안국·커피한약방 을지로 2곳이다.
나머지 7곳은 원문 공간 설명을 보존하되 S/N은 미평가다. 사진 링크를 붙였다는
이유로 MBTI 점수를 부여하지 않는다. `catalog_descriptions`의 짧은 발췌문만
새로운 S/N 근거이며 기존 `catalog_instagram` 임베드 목록은 계속 표시 전용이다.
키 170cm 실내외 기준 및 별도 T/F 유형 보너스는 제거했다.
[수집 범위·계산식·J/P 검토안](PROFILE_FIT.md)을 참고한다.
