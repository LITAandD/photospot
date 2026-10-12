# 포토스팟 출시 상태

기준: 2026-10-12. 웹 체험은 [운영 주소](https://photospot-nu.vercel.app/home)에 배포합니다. Android·iOS는 출시 후보이며 스토어 제출을 완료한 상태가 아닙니다.

현재 검토·수정 범위와 검증 결과는 [37개 항목 검토 결과](REVIEW_2026-10-12.md)에 한 번만 기록합니다. 이전 문서의 서로 다른 테스트 수는 당시 단계별 실행 결과였으며 현재 통과 수로 사용하지 않습니다. 최종 커밋의 [CI 실행](https://github.com/LITAandD/photospot/actions/workflows/ci.yml)을 기준으로 확인하세요.

## 현재 동작

- 기본 `catalog` 백엔드에서 웹·인증 API가 같은 장소·점수·사진을 사용합니다. PostgreSQL은 인증·동의·북마크·피드백·결제 상태를 보관합니다. `scenes`는 기존 사진 분석용 대체 백엔드입니다.
- 전체 정합도 점수를 우선 정렬하고 평가 범위와 거리 등을 동점 기준으로 사용합니다. 키는 실내/실외 추천 점수에 사용하지 않습니다. 개인 오행·촬영일 일진은 선택 시 반영합니다.
- 피드는 썸네일·장소명·정합도·운영시간·거리만 표시합니다. 상세에는 파이차트·지표 설명과 사진 위 포즈 스케치를 제공합니다. 검수된 사진은 실제 인물 비율을 적용하고 수동 크기 보정도 가능합니다.
- 재사용 권한을 확인한 사진만 공개합니다. 공식 브랜드 사진은 기본 제외하며 인스타그램은 검증된 공개 원본 링크를 사용합니다. 변경 금지 사진은 자르거나 스케치를 겹치지 않습니다.
- 공식 날짜별 운영시간은 게시된 날짜에만 사용합니다. 현재 추천 대상 공식 지점 3곳은 10/12 확인, 10/18까지 갱신했습니다. 주간 갱신 workflow는 PR을 생성하며 운영 반영에는 병합이 필요합니다.

## 재현 검사

```sh
python -m pip install -r requirements-dev.txt -r requirements-quality.txt
python -m scripts.check_dependencies
python -m ruff check api pipeline saju scripts tests
python -m mypy
python -m pytest tests -q
npm --prefix client test
npm --prefix app run typecheck
npm --prefix app test
```

CI는 PostGIS 서비스에서 `scripts.migrate --seed`, 재실행, 상태 확인, 전체 Python 테스트, OpenAPI 일치, 사진-점수 무결성, 모든 플랫폼 export와 Playwright 웹 여정을 실행합니다. `security` 작업은 pip-audit와 npm audit 결과를 첨부합니다. Python은 발견 시, 클라이언트는 high/critical, 앱은 현재 critical을 차단합니다. 낮은 등급과 기존 Expo high/moderate 경고도 보고서에 보존합니다.

추가 검토의 변경·검증 범위는 [16건 반영 기록](REVIEW_FOLLOWUP_2026-10-12.md)에 정리했습니다. 영업시간 갱신은 빈 카탈로그·25% 초과 퇴역을 차단하고, 부분 성공은 실패 지점의 기존 날짜를 보존한 채 PR로 올립니다.

`artifacts/`는 테스트·수집 시 생성되는 로컬 출력 폴더이며 Git에 포함되지 않습니다. 공개 검증 자료는 CI 실행 페이지의 `ui-screenshots`, `security-reports`, 데이터 갱신 작업의 `data-refresh-reports`를 확인하세요. 배포 데이터 출처·해시·행 수는 추적되는 [카탈로그 manifest](catalog/places.manifest.json)에 있습니다.

## 운영 전 남은 범위

실제 OAuth/Meta 승인·RevenueCat 결제·Apple 탈퇴를 운영 계정과 실기기에서 검증해야 합니다. CI의 테스트 제공자와 가짜 HTTP 검사는 이를 대신하지 않습니다. 여러 서버 인스턴스에 걸친 요청 제한은 별도 공용 저장소 또는 WAF가 필요합니다. 공개 이미지 이용 허락, 저장소 배포 라이선스, 다국어 지원과 스토어 설정은 각각의 범위로 관리합니다.
