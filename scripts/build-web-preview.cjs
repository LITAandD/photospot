/** Build a public browser demo without loading local environment files. */
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const env = {
  ...process.env,
  CI: '1',
  EXPO_NO_DOTENV: '1',
  EXPO_OFFLINE: '1',
  EXPO_PUBLIC_DEMO: '1',
  EXPO_PUBLIC_DEV_LOGIN: '0',
  EXPO_PUBLIC_PREVIEW_API_URL: '',
};

// --- 정책 문서 주소 (legal-consent) -------------------------------------------
// 웹 빌드는 같은 도메인의 정적 페이지(app/public/policies, 아래에서 dist로 복사)를 기본값으로 쓴다.
// 배포 환경이 절대 HTTPS 주소를 넣으면 그 값을 유지한다. 스토어 빌드는 release-config.cjs가 절대 주소를 요구한다.
for (const [key, file] of Object.entries({
  EXPO_PUBLIC_PRIVACY_URL: 'privacy', EXPO_PUBLIC_TERMS_URL: 'terms',
  EXPO_PUBLIC_LOCATION_TERMS_URL: 'location-terms', EXPO_PUBLIC_ACCOUNT_DELETION_URL: 'account-deletion',
})) env[key] ||= `/policies/${file}.html`;

function npm(directory, args) {
  const result = spawnSync('npm', args, {
    cwd: path.join(root, directory), env, stdio: 'inherit',
    shell: process.platform === 'win32', windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

npm('client', ['ci', '--no-audit', '--no-fund']);
npm('client', ['run', 'build']);
npm('app', ['ci', '--no-audit', '--no-fund']);
npm('app', ['exec', '--', 'expo', 'export', '--platform', 'web', '--output-dir', 'dist']);
require('node:fs').copyFileSync(path.join(root, 'deploy/vercel/404.html'), path.join(root, 'app/dist/404.html'));
const fs = require('node:fs');

// --- 공유 미리보기·검색·설치 메타 (ux-flows) ----------------------------------
// 카카오톡·슬랙·X 링크 미리보기(og:*·twitter:*), 검색 스니펫(description), 파비콘·홈 화면 아이콘·manifest, canonical·theme-color.
// 이미지·아이콘은 app/public 의 정적 파일(아래 legal-consent 블록이 dist 로 복사; /tmp/claude-0/fix/ux-flows/gen_assets.py 로 생성).
// 한 HTML 을 모든 경로가 공유하므로 canonical·og:url 은 대문 주소로 두고, 앱이 경로 변경 때 현재 경로로 바꾼다 (app/app/_layout.tsx).
// 배포 도메인이 바뀌면 PUBLIC_BASE_URL(배포 환경 변수) 또는 아래 기본값 한 곳만 고친다.
const PUBLIC_WEB_URL = (process.env.PUBLIC_BASE_URL || 'https://photospot.litaandd.com').replace(/\/+$/, '');
const TITLE = '포토스팟 · 나에게 어울리는 촬영 장소 추천';
const DESCRIPTION = '퍼스널컬러·체형·빛에 맞는 사진 명소를 찾아 드려요. 촬영일과 위치만 고르면 나에게 어울리는 장소를 추천해요.';
const META = [
  `<meta name="description" content="${DESCRIPTION}">`,
  '<meta name="theme-color" content="#F6F3EE">',
  '<meta property="og:type" content="website">',
  '<meta property="og:site_name" content="포토스팟">',
  `<meta property="og:title" content="${TITLE}">`,
  `<meta property="og:description" content="${DESCRIPTION}">`,
  `<meta property="og:url" content="${PUBLIC_WEB_URL}/">`,
  `<meta property="og:image" content="${PUBLIC_WEB_URL}/og.png">`,
  '<meta property="og:image:width" content="1200">',
  '<meta property="og:image:height" content="630">',
  '<meta property="og:image:alt" content="포토스팟 — 나에게 어울리는 촬영 장소 추천">',
  '<meta property="og:locale" content="ko_KR">',
  '<meta name="twitter:card" content="summary_large_image">',
  `<meta name="twitter:title" content="${TITLE}">`,
  `<meta name="twitter:description" content="${DESCRIPTION}">`,
  `<meta name="twitter:image" content="${PUBLIC_WEB_URL}/og.png">`,
  `<link rel="canonical" href="${PUBLIC_WEB_URL}/">`,
  '<link rel="icon" href="/favicon.ico" sizes="48x48">',
  '<link rel="apple-touch-icon" href="/apple-touch-icon.png">',
  '<link rel="manifest" href="/manifest.json">',
  // 번들 실행 전에 글꼴 CSS 요청을 시작한다. app/src/fonts.web.ts 가 id=app-fonts 링크를 재사용하며 cssRules 를 읽으려면 crossorigin 이 필요하다.
  '<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>',
  '<link id="app-fonts" rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Gowun+Batang:wght@700&family=IBM+Plex+Sans+KR:wght@400;500;600&display=swap" crossorigin="anonymous">',
].join('\n    ');
function withMeta(html) {
  if (html.includes('property="og:title"')) return html;           // 다시 실행해도 한 번만
  if (!html.includes('<title>포토스팟</title>')) throw new Error('index.html 에서 <title>포토스팟</title> 을 찾지 못했어요 — 메타 주입 위치를 확인해 주세요');
  return html.replace('<title>포토스팟</title>', `<title>포토스팟</title>\n    ${META}`);
}
const entry = withMeta(fs.readFileSync(path.join(root, 'app/dist/index.html'), 'utf8').replace('<html lang="en">', '<html lang="ko">'));
fs.writeFileSync(path.join(root, 'app/dist/index.html'), entry);
fs.writeFileSync(path.join(root, 'deploy/vercel/web-entry.html'), entry);

// --- 정적 정책 페이지 복사 (legal-consent) ------------------------------------
// app/public/** → app/dist/** (expo export도 public을 복사하지만 CLI 버전과 무관하게 보장한다).
// /policies/*.html은 JS 없이 읽히므로 스토어 심사·개발자 콘솔·크롤러가 그대로 확인할 수 있다.
const publicDir = path.join(root, 'app/public');
if (fs.existsSync(publicDir)) fs.cpSync(publicDir, path.join(root, 'app/dist'), { recursive: true });
for (const file of ['privacy', 'terms', 'location-terms', 'account-deletion']) {
  if (!fs.existsSync(path.join(root, 'app/dist/policies', `${file}.html`))) throw new Error(`정책 페이지가 빠졌어요: policies/${file}.html`);
}

// --- 공유 자산 확인 (ux-flows) ------------------------------------------------
// 위 복사로 dist 에 들어온 og.png·favicon.ico·apple-touch-icon.png·manifest.json — 메타가 가리키는 파일이 빠지면 빌드를 멈춘다.
const SHARE_ASSETS = ['og.png', 'favicon.ico', 'apple-touch-icon.png', 'manifest.json', 'icon-192.png', 'icon-512.png'];
for (const file of SHARE_ASSETS) {
  if (!fs.existsSync(path.join(root, 'app/dist', file))) throw new Error(`공유 자산이 빠졌어요: app/public/${file}`);
}
