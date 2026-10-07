# Vercel 웹 체험 배포

저장소 루트의 `vercel.json`과 `pyproject.toml`로 웹 체험 버전을 배포합니다.
정식 회원 API·PostGIS·작업 처리기 배포와는 별도입니다.

## 구성

- Expo 웹 번들을 `app/dist`에 생성하고 Vercel CDN에서 제공합니다.
- FastAPI 진입점은 `deploy.vercel.index:app`입니다. `/preview/*`와 `/health`를 처리합니다.
- 브라우저는 같은 도메인의 `/preview/*`를 호출합니다. 별도 API 주소·CORS·비밀키 설정이 필요하지 않습니다.
- 프로필·오행 비율·저장 목록은 각 브라우저의 localStorage에 남습니다. 실제 회원가입·소셜 로그인·업로드·결제·GPT 분석은 제공하지 않습니다.
- 서버에는 공개 장소 스냅샷 `catalog/places.sqlite3`만 포함합니다. 읽기 전용 배포 파일을 수정하지 않도록 프로세스별 임시 디렉터리에 복사하여 조회합니다. 개인 계산 입력은 저장하지 않습니다.
- 클라이언트 경로를 직접 열거나 새로고침해도 `index.html`로 연결됩니다.

## GitHub에서 가져오기

1. Vercel에서 `LITAandD/photospot` 저장소를 가져옵니다.
2. Root Directory는 저장소 루트(`.`), Framework Preset은 FastAPI입니다.
3. Build Command는 `node scripts/build-web-preview.cjs`이며 `vercel.json`에 설정되어 있습니다. Output Directory와 Install Command는 기본값으로 둡니다.
4. 환경변수는 추가하지 않아도 됩니다. 특히 로컬 `.env`, 서버 JWT 키, 소셜 로그인 키를 업로드하지 않습니다.
5. 배포 완료 후 `/health`, 첫 화면, 체험 로그인, 추천, 사주 계산, 장소 상세의 직접 접속을 확인합니다.

`pyproject.toml`은 웹 체험에 필요한 Python 패키지만 지정합니다. 전체 API와 작업 처리기는 기존 `requirements.txt`를 계속 사용합니다.
`scripts/build-web-preview.cjs`는 클라이언트와 앱 의존성을 설치하고, 로컬 `.env`를 읽지 않은 상태에서 체험용 웹 번들을 만듭니다.

## 로컬 검증

```sh
node scripts/build-web-preview.cjs
python -m pytest tests/test_vercel_preview.py tests/test_personal_preview.py -q
python -m uvicorn deploy.vercel.index:app --host 127.0.0.1 --port 8082
```

마지막 명령은 실제 배포용 웹 번들과 계산 API를 같은 주소에서 제공합니다.
기존 `npm --prefix app run demo` 방식은 개발용 8081/8001 서버를 계속 사용합니다.

## 추천 시작 장소

추천 화면은 현위치를 먼저 확인하고, 위치가 확보된 뒤 주변 추천을 요청합니다. 권한 거부·시간 초과·국외 위치에서는 지역 선택을 안내하며 임의의 서울 좌표로 조회하지 않습니다. 위치 확인 중 수동으로 고른 장소는 뒤늦은 위치 응답이 덮어쓰지 않습니다. 위치는 프로필에 저장하거나 계속 추적하지 않습니다.

| 도시 | 선택할 수 있는 시작 권역 |
| --- | --- |
| 서울 · 7곳 | 종로·북촌, 성수·서울숲, 홍대·연남, 여의도·한강, 잠실·석촌호수, 남산·이태원, 강남·코엑스 |
| 부산 · 5곳 | 해운대·미포, 광안리, 남포·감천, 영도·흰여울, 송정·기장 해안 |
| 강릉 · 3곳 | 경포·초당, 안목·남항진, 주문진 |

권역은 촬영 여행을 위한 시작점이며 행정구역 경계 필터가 아닙니다. `app/src/recommendation-regions.ts`의 대표 좌표에서 기본 5km를 검색하고, 1·3·5·10·30·50km로 조절할 수 있습니다. 분류는 [서울 공식 관광정보](https://korean.visitseoul.net/attractions), [부산 공식 도보여행 안내](https://www.visitbusan.net/kr/index.do?lang_cd=ko&menuCd=DOM_000000202004001000&uc_seq=768), [한국관광공사의 주문진 안내](https://english.visitkorea.or.kr/svc/contents/contentsView.do?vcontsId=174269)와 공개 장소 카탈로그를 참고해 구성했습니다.

위치 획득 실패와 비동기 요청 충돌 검증: `node app/scripts/test-starting-place.cjs`.

## 달력과 종합 오행 추천

기본 추천과 오행·일진 추천의 촬영일은 같은 달력 컴포넌트에서 고릅니다. 기본 추천은 날짜 선택 즉시 조회하고, 오행 화면에서는 선택한 날짜와 저장된 오행으로 추천 보기 버튼을 누를 때 함께 계산합니다. 생년월일 입력과 촬영일 선택은 별도입니다.

공개 웹의 카탈로그 추천은 `personal70_daily30_v1` 기준을 사용합니다.

- 저장된 오행 비율의 반올림 합계를 100으로 정규화하고, 20% 미만인 오행을 보완 후보로 둡니다. 개인 보완 점수는 `max(0, 20 - 정규화 비율) / 20 × 70`입니다.
- 촬영일은 선택한 한국 달력 날짜 그대로 일주를 구하고, 일진 천간의 오행을 사용합니다. 일진→장소 상생 30점, 동일 24점, 장소→일진 상생 18점, 장소→일진 상극 6점, 일진→장소 상극 0점을 더합니다.
- 합계 상위 두 후보를 우선 대상으로 정하고, 두 번째 점수의 동점은 함께 포함합니다. 후보가 하나면 하나만 선택합니다. 개인 비율이 모두 같으면 개인 보완 점수는 0이고 전체 오행에서 일진 관계로 고릅니다.
- 장소에서 근거가 확인된 우선 대상 오행 중 최고 점수를 사용합니다. 여러 오행 태그를 합산해 점수를 부풀리지 않습니다. 근거 없는 오행은 부여하지 않으며, 우선 오행에 맞는 장소가 없으면 빈 결과를 안내합니다.
- 장소 종합 점수를 사진 유무보다 먼저 적용합니다. 동점에서는 기존 사진·사진 정합도·프로필·인기도·거리 기준을 적용합니다. 목록과 상세에 같은 점수 및 이유를 반환하고, 기본 사진 정합도 점수에는 오행 점수를 섞지 않습니다.

상생·상극 방향은 [한국학중앙연구원 오행 해설](https://waks.aks.ac.kr/rsh/dir/rview.aspx?dataID=AKS-2013-CKD-1240001_DIC%4000015185&rshID=AKS-2013-CKD-1240001)을 참고했습니다. 20% 기준, 70:30 가중치와 관계별 점수는 포토스팟의 취향 탐색 설계이며 전통 명리의 용신 판정이나 효과가 검증된 사진 평가법을 뜻하지 않습니다. 기존 PostGIS 장면 채점 함수와 샘플 태그 엔진은 이 웹 카탈로그 정렬과 별도입니다.

검증: `node app/scripts/test-calendar.cjs`, `python -m pytest tests/test_deficient_recommendations.py -q`.

공개 서버의 입력 처리와 브라우저 저장 범위는 앱의 웹 체험 정보 처리 안내에서 확인할 수 있습니다. 실제 회원 서비스로 전환하려면 별도의 인증·DB·운영 정책 설정이 필요합니다.
