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

공개 서버의 입력 처리와 브라우저 저장 범위는 앱의 웹 체험 정보 처리 안내에서 확인할 수 있습니다. 실제 회원 서비스로 전환하려면 별도의 인증·DB·운영 정책 설정이 필요합니다.
