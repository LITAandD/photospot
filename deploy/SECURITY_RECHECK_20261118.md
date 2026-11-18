# 보안 검사 재점검 · 2026-11-18
main 기준: 3ba7a3866c6b329583ea5c921a46ca9a9c92a5ad. 운영 배포 없음.

## 서로 다른 두 실패
- [#34 기존 CI](https://github.com/LITAandD/photospot/actions/runs/44207655042): security 로그의 실패는 `Finding is absent from dependency graph: compat/glob-match/node_modules/picomatch`이다. pip-audit와 client 검사 실패가 아니다.
- npm file 링크의 의존성을 별칭 node_modules 경로에서 해석하던 감사 도구를 실제 링크 대상 디렉터리에서 해석하도록 수정했다. 누락 의존성을 무시하지 않으며, 연결되지 않은 설치는 여전히 실패한다.
- 수정 후 실제 감사 응답을 재생하면 별개의 미검토 취약점 [GHSA-fc5q-39xc-vjpf](https://github.com/advisories/GHSA-fc5q-39xc-vjpf)에서 정상적으로 차단된다. 2026-11-17 갱신 공지는 picomatch <=4.0.7을 포함하고 확인 시점에 패치 버전이 없다. 설치된 4.0.7도 안전하다고 간주할 수 없다.

## 검증과 제한
- `node app/scripts/test-audit.cjs` 통과: 링크 내부/루트의 다른 버전, 경로 추적, 미승인 advisory 및 그래프에 없는 설치 차단.
- 실제 app 감사: 29개 패키지 항목(중간 7, 높음 22, 치명적 0). 이는 독립 취약점 수와 다르다.
- 보안 예외, 권한, 의존성 버전, 검사 강도는 변경하지 않았다. 이 수정만으로 security CI가 통과한다고 보고하지 않는다.
- 의존성 교체 또는 업스트림 패치의 호환성 검증은 별도 필요하다. 현재 새 PR들의 security 실패를 일정/사진/공유 기능 회귀 실패와 구분해야 한다.
