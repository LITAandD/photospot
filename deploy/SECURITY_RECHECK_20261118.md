> 2026-11-23 재검토: 아래는 11/18 당시의 이력이다. GHSA-fc5q-39xc-vjpf는 11/18 보안 문제가 아니라는 사유로 철회됐다. 공식 권고와 교체 전 lockfile을 다시 확인해 picomatch 교체만 되돌린다. 링크 의존성 감사 수정과 테스트는 유지한다. 현재 감사는 picomatch 경고 없이 moderate 9/high 2, 3종 advisory이며 사라진 deepmerge 예외만 삭제했다. 새 예외·기준 완화는 없다.

# 보안 검사 재점검 · 2026-11-18
main 기준: 3ba7a3866c6b329583ea5c921a46ca9a9c92a5ad. 운영 배포 없음.

## 서로 다른 두 실패
- [#34 기존 CI](https://github.com/LITAandD/photospot/actions/runs/44207655042): security 로그의 실패는 `Finding is absent from dependency graph: compat/glob-match/node_modules/picomatch`이다. pip-audit와 client 검사 실패가 아니다.
- npm file 링크의 의존성을 별칭 node_modules 경로에서 해석하던 감사 도구를 실제 링크 대상 디렉터리에서 해석하도록 수정했다. 누락 의존성을 무시하지 않으며, 연결되지 않은 설치는 여전히 실패한다.
- 수정 후 실제 감사 응답을 재생하면 별개의 미검토 취약점 [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)에서 정상적으로 차단된다. 2026-11-17 갱신 공지는 picomatch <=4.0.7을 포함하고 확인 시점에 패치 버전이 없다. 설치된 4.0.7도 안전하다고 간주할 수 없다.

## 최초 검증과 제한 (교체 전)
- `node app/scripts/test-audit.cjs` 통과: 링크 내부/루트의 다른 버전, 경로 추적, 미승인 advisory 및 그래프에 없는 설치 차단.
- 실제 app 감사: 29개 패키지 항목(중간 7, 높음 22, 치명적 0). 이는 독립 취약점 수와 다르다.
- 보안 예외, 권한, 의존성 버전, 검사 강도는 변경하지 않았다. 이 수정만으로 security CI가 통과한다고 보고하지 않는다.
- 의존성 교체 또는 업스트림 패치의 호환성 검증은 별도 필요하다. 현재 새 PR들의 security 실패를 일정/사진/공유 기능 회귀 실패와 구분해야 한다.

## 후속 수정: 취약 의존성 제거
- 11/18 재확인 당시 npm 최신 picomatch는 4.0.7이며 해당 advisory의 패치 버전은 없다. 기존 감사를 통과시키기 위한 예외를 추가하지 않고 registry picomatch 2.3.2·4.0.7 설치 세 곳을 제거한다.
- `compat/pattern-match`는 독립적인 Minimatch 11.0.9 비정규식 엔진 위의 제한된 호환 계층이다. picomatch 코드를 복사하거나 패키지 이름만 바꾼 것이 아니다. Expo/Jest/anymatch의 실제 호출부와 기존 Micromatch 결과를 검사한다.
- 기존 exceptions 배열 4건(식별자·심각도·설치 버전·경로 해시·만료일)은 그대로다. 새 엔진과 어댑터가 웹·Android·iOS 실행 번들에 들어오면 실패하도록 runtime 차단 항목만 추가한다. 감사 도구의 누락·새 advisory·critical·경로 변경·만료 차단은 유지한다.
- 범위 밖 Expo/React 버전 및 기존 예외 의존성을 보존하고 새 엔진의 원본 npm 메타데이터·integrity만 잠금 파일에 연결한다. 정상 `npm ci`와 전체 앱 빌드로 검증한다.
- 실제 npm 감사: picomatch advisory 제거, 기존 3종 advisory만 탐지되어 기존 게이트 통과(패키지 항목 11: moderate 9, high 2). 취약점이 0개라는 의미는 아니다. 기존 예외 4건은 만료 전 별도 재검토 대상이다.
- 최종 CI 결과와 #38~#42 재검증 링크는 각 Draft PR 본문에 기록한다. main 병합·운영 배포·권한 변경은 하지 않는다.
