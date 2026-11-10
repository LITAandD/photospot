// 위치정보·가입 동의 흐름: 홈은 마운트 시 GPS를 부르지 않고, 좌표는 동의 뒤에만 조회하며, 로그인은 세 필수 동의가 모두 있어야 열린다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

const RN = ['ActivityIndicator', 'Pressable', 'Text', 'View', 'ScrollView', 'TextInput'];
const UI = ['Body', 'Button', 'Card', 'Chip', 'ErrorBox', 'Muted', 'Screen', 'Title', 'Label', 'Field', 'OptionRow', 'StepHeader'];
const tags = (names) => Object.fromEntries(names.map((n) => [n, n]));
const transpile = (file) => ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText;
/** 소스 모듈을 실행한다. stubs에 없는 '@/...' 모듈은 실제 소스를 다시 불러온다 (recommendation-regions, starting-place, policy-links). */
function load(relative, stubs, globals = {}) {
  const file = path.resolve(__dirname, '..', relative);
  const mod = { exports: {} };
  const context = { module: mod, exports: mod.exports, setTimeout, clearTimeout, Error, Promise, Math, Number, Date, Object, Map, Set, console, process: { env: globals.env ?? {} }, ...globals,
    require(name) {
      if (name === 'react' || name === 'react/jsx-runtime') return require(name);
      if (name in stubs) return stubs[name];
      if (name.startsWith('@/')) {
        const base = 'src/' + name.slice(2);
        for (const ext of ['.ts', '.tsx']) if (fs.existsSync(path.resolve(__dirname, '..', base + ext))) return load(base + ext, stubs, globals);
      }
      if (name.startsWith('./')) return load(path.join(path.dirname(relative), name) + '.ts', stubs, globals);
      throw new Error(`stub 없는 모듈: ${name} (from ${relative})`);
    } };
  vm.runInNewContext(transpile(file), context, { filename: file });
  return mod.exports;
}
const flush = () => act(async () => { await Promise.resolve(); await Promise.resolve(); });

(async () => {
  // --- local-flags.web: 브라우저 저장소에 남기고, 막히면 메모리로 --------------------------------
  const store = new Map();
  const localStorage = { getItem: (k) => store.get(k) ?? null, setItem: (k, v) => store.set(k, v), removeItem: (k) => store.delete(k) };
  const flags = load('src/local-flags.web.ts', {}, { localStorage });
  assert.equal(await flags.readFlag('location-consent'), false);
  await flags.writeFlag('location-consent', true);
  assert.equal(store.get('photospot.flag.location-consent'), '1');
  assert.equal(await flags.readFlag('location-consent'), true);
  await flags.writeFlag('location-consent', false);
  assert.equal(store.has('photospot.flag.location-consent'), false);
  const blocked = load('src/local-flags.web.ts', {}, { localStorage: { getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); } } });
  await blocked.writeFlag('beta', true);
  assert.equal(await blocked.readFlag('beta'), true);

  // --- starting-place: 실패·거부 시 마지막 시작 장소(기본 프리셋)로 돌아간다 ---------------------
  const { createStartingPlace } = load('src/starting-place.ts', {});
  const { DEFAULT_PHOTO_READY_AREA, SUPPORTED_REGIONS } = load('src/recommendation-regions.ts', {});
  const states = [];
  const denied = createStartingPlace(async () => { throw new Error('권한 거부'); }, (s) => states.push(s), 12000, DEFAULT_PHOTO_READY_AREA);
  await denied.locate();
  assert.equal(states[0].place.id, 'seoul-jongno'); assert.equal(states[0].locating, true);  // 확인 중에도 기본 장소를 유지
  assert.equal(states[1].place.id, 'seoul-jongno'); assert.equal(states[1].note, '권한 거부');
  denied.select(DEFAULT_PHOTO_READY_AREA);

  // --- StartingPlacePicker: 동의 전에는 onLocate를 부르지 않는다 ----------------------------------
  const opened = [], events = [];                                   // 계측 스텁: 이벤트 이름·작은 속성만 기록(좌표 없음)
  const analytics = { track: async (event, props = {}) => { events.push([event, props]); return true; } };
  const picker = load('src/components/starting-place-picker.tsx', {
    'react-native': { ...tags(RN), Platform: { OS: 'web' }, useWindowDimensions: () => ({ width: 390 }), StyleSheet: { create: (s) => s }, Linking: { openURL: async (url) => { opened.push(url); } } },
    './ui': tags(UI), '@/theme': { colors: {}, fonts: {} }, '@/analytics': analytics,
  }, { env: { EXPO_PUBLIC_LOCATION_TERMS_URL: '/policies/location-terms.html' } });
  const idle = { place: DEFAULT_PHOTO_READY_AREA, locating: false, note: null };
  const button = (tree, title) => tree.root.findAll((n) => n.type === 'Button' && n.props.title === title);
  let calls;
  const mount = async (consented) => {
    calls = [];
    let tree;
    await act(() => { tree = create(React.createElement(picker.StartingPlacePicker, { state: idle, consented, onConsent: () => calls.push('consent'), onLocate: () => calls.push('locate'), onSelect: () => calls.push('select') })); });
    return tree;
  };
  let tree = await mount(false);
  assert.equal(button(tree, '내 주변에서 찾기').length, 1);
  await act(() => button(tree, '내 주변에서 찾기')[0].props.onPress());
  assert.deepEqual(calls, []);
  assert.equal(button(tree, '동의하고 내 주변에서 찾기').length, 1, '동의 시트가 열린다');
  assert.ok(tree.root.findAll((n) => n.type === 'Muted').some((n) => String(n.props.children).includes('저장하지 않으며')));
  await act(() => tree.root.find((n) => n.type === 'Pressable' && n.props.accessibilityRole === 'link').props.onPress());
  assert.deepEqual(opened, ['/policies/location-terms.html']);
  await act(() => button(tree, '다음에 할게요')[0].props.onPress());
  assert.deepEqual(calls, []);
  assert.equal(button(tree, '동의하고 내 주변에서 찾기').length, 0);
  await act(() => button(tree, '내 주변에서 찾기')[0].props.onPress());
  await act(() => button(tree, '동의하고 내 주변에서 찾기')[0].props.onPress());
  assert.deepEqual(events, [['gps_allow', {}]], '동의 직후 gps_allow 이벤트 한 번, 좌표 없음');
  assert.deepEqual(calls, ['consent', 'locate']);
  await act(() => tree.unmount());
  tree = await mount(true);
  await act(() => button(tree, '내 주변에서 찾기')[0].props.onPress());
  assert.deepEqual(calls, ['locate'], '이미 동의했으면 바로 조회');
  assert.equal(button(tree, '동의하고 내 주변에서 찾기').length, 0);
  await act(() => tree.unmount());

  // --- Home: 마운트 시 GPS 없음, 기본 좌표는 종로·북촌, 동의 → 조회 → 좌표 사용, 미지원 지역은 안내 ------
  const gps = [], recs = [], written = [];
  let position = { lat: 35.1509, lng: 129.1191 };
  const stubFlags = { readFlag: async () => false, writeFlag: async (name, value) => { written.push([name, value]); } };
  const useAsync = (fn) => { const r = fn(); if (r && r.catch) r.catch(() => {}); return { data: null, loading: false, error: null, reload() {} }; };
  const home = load('app/home.tsx', {
    '@photospot/client': {}, 'expo-router': { useRouter: () => ({ push() {}, replace() {} }) },
    'react-native': { ...tags(RN), Platform: { OS: 'web' }, useWindowDimensions: () => ({ width: 390 }), StyleSheet: { create: (s) => s }, Linking: { openURL: async () => {} } },
    '@/api': { today: () => '2026-11-10', api: { billing: async () => ({ configured: false }), syncBilling: async () => ({}), sponsorships: async () => null,
      grantConsent: async (type) => { written.push(['server', type]); },
      getRecommendations: async (q) => { recs.push(q); return { items: [], missing_inputs: [], catalog: null, score_weights: [] }; } } },
    '@/components/ui': tags(UI), '@/components/calendar-field': { CalendarField: 'CalendarField' }, '@/components/place-recommendation': { PlaceRecommendation: 'PlaceRecommendation' },
    '@/components/score-explanation': { ScoringGuide: 'ScoringGuide' }, '@/components/sponsored-places': { SponsoredPlaces: 'SponsoredPlaces' },
    '@/components/starting-place-picker': { StartingPlacePicker: 'StartingPlacePicker' }, '@/components/start-over': { StartOver: 'StartOver' },
    '@/hooks': { errorMessage: (e) => e.message, useAsync, useRefocus() {} }, '@/theme': { colors: {}, fonts: {} },
    '@/place-groups': { PLACE_GROUPS: [{ value: 'all', label: '전체' }], placeGroupLabel: () => '전체' },
    '@/current-location': { getCurrentLocation: async () => { gps.push(position); return position; } }, '@/local-flags': stubFlags,
    '@/analytics': analytics,
  });
  let homeTree;
  await act(() => { homeTree = create(React.createElement(home.default)); });
  await flush();
  assert.equal(gps.length, 0, '마운트만으로는 위치를 조회하지 않는다');
  assert.ok(recs.length && recs.every((q) => q.lat === 37.5796 && q.lng === 126.977), '기본 시작 장소는 종로·북촌');
  const pickerProps = () => homeTree.root.findByType('StartingPlacePicker').props;
  assert.equal(pickerProps().consented, false);
  assert.equal(pickerProps().state.place.id, 'seoul-jongno');
  const banner = () => homeTree.root.findAll((n) => n.type === 'Text' && String(n.props.children.join ? n.props.children.join('') : n.props.children).includes('베타예요'));
  assert.equal(banner().length, 1, '베타 안내 한 줄');
  assert.equal(banner()[0].props.children.join(''), `지금은 ${SUPPORTED_REGIONS} 지역 베타예요`);
  await act(() => homeTree.root.find((n) => n.type === 'Pressable' && n.props.accessibilityLabel === '베타 안내 닫기').props.onPress());
  assert.equal(banner().length, 0);
  assert.deepEqual(written, [['beta-banner-dismissed', true]]);
  await act(() => pickerProps().onConsent());
  assert.deepEqual(written.slice(1), [['location-consent', true], ['server', 'location']], '기기 플래그와 계정 동의 기록을 함께 남긴다');
  assert.equal(pickerProps().consented, true);
  assert.equal(gps.length, 0, '동의만으로는 아직 조회하지 않는다');
  await act(async () => { pickerProps().onLocate(); });
  await flush();
  assert.equal(gps.length, 1);
  assert.equal(pickerProps().state.place.id, 'current');
  assert.ok(recs.some((q) => q.lat === 35.1509 && q.lng === 129.1191), '동의 후 현위치 좌표로 추천을 요청한다');
  position = { lat: 35.8714, lng: 128.6014 };  // 대구: 수집 반경 밖
  await act(async () => { pickerProps().onLocate(); });
  await flush();
  assert.equal(gps.length, 2);
  assert.match(pickerProps().state.note, /추천하지 않는 지역/);
  assert.equal(pickerProps().state.place.id, 'current', '직전 시작 장소를 유지하고 좌표를 바꾸지 않는다');
  assert.ok(!recs.some((q) => q.lat === 35.8714), '미지원 좌표는 서버로 보내지 않는다');
  await act(() => homeTree.unmount());

  // --- Login: 약관·개인정보·14세 세 필수 동의가 모두 있어야 로그인 버튼이 열린다 ------------------------
  const logins = [];
  const login = load('app/login.tsx', {
    '@photospot/client': {}, 'expo-router': { useRouter: () => ({ push() {}, replace() {} }) },
    'react-native': { ...tags(RN), Platform: { OS: 'web' }, useWindowDimensions: () => ({ width: 390 }), StyleSheet: { create: (s) => s }, Linking: { openURL: async (url) => { opened.push(url); } } },
    '@/api': { DEMO: false, DEV_LOGIN: true, api: { authProviders: async () => ({ providers: ['google'] }) } },
    '@/components/brand-mark': { BrandMark: 'BrandMark' }, '@/components/photo-showcase': { PhotoShowcase: 'PhotoShowcase' }, '@/components/ui': tags(UI), '@/state/onboarding': { useOnboarding: () => ({ dispatch() {} }) },
    '@/hooks': { errorMessage: (e) => e.message, useAsync: () => ({ data: { providers: ['google'] }, error: null, reload() {} }) },
    '@/auth/providers': { devLogin: async (id) => { logins.push(id); return { profile_exists: true }; }, isAppleAvailable: async () => false, isExpoGo: false,
      LoginCancelled: class extends Error {}, PROVIDERS: [{ id: 'google', label: 'Google', bg: '#fff', fg: '#000', run: async () => { logins.push('google'); return { profile_exists: true }; } }] },
    '@/theme': { colors: {}, fonts: {} }, '@/analytics': analytics, '@/state/auth-session': { takeIntendedRoute: () => null },
  }, { env: { EXPO_PUBLIC_TERMS_URL: 'https://photospot.app/policies/terms.html' } });
  let loginTree;
  await act(() => { loginTree = create(React.createElement(login.default)); });
  await flush();
  const boxes = () => loginTree.root.findAll((n) => n.type === 'Pressable' && n.props.accessibilityRole === 'checkbox');
  const byLabel = (label) => boxes().find((n) => n.props.accessibilityLabel === label);
  assert.deepEqual(boxes().map((n) => n.props.accessibilityLabel), ['모두 동의', '[필수] 서비스 이용약관 동의', '[필수] 개인정보 수집·이용 동의', '[필수] 만 14세 이상입니다']);
  assert.ok(boxes().every((n) => n.props.accessibilityState.checked === false && n.props['aria-checked'] === false));
  const loginButtons = () => loginTree.root.findAll((n) => n.type === 'Pressable' && n.props.accessibilityRole === 'button' && n.props.disabled !== undefined);
  assert.equal(loginButtons().length, 2);
  assert.ok(loginButtons().every((n) => n.props.disabled && n.props.accessibilityState.disabled));
  await act(() => loginButtons()[0].props.onPress());
  assert.deepEqual(logins, [], '동의 전 로그인 호출 없음');
  await act(() => byLabel('[필수] 서비스 이용약관 동의').props.onPress());
  await act(() => byLabel('[필수] 개인정보 수집·이용 동의').props.onPress());
  assert.ok(loginButtons().every((n) => n.props.disabled), '14세 확인 없이는 닫혀 있다');
  assert.ok(loginTree.root.findAll((n) => n.type === 'Text').some((n) => String(n.props.children).includes('보유: 회원 탈퇴 시까지')), '수집 항목·보유기간 요약 표시');
  await act(() => byLabel('[필수] 만 14세 이상입니다').props.onPress());
  assert.ok(loginButtons().every((n) => !n.props.disabled));
  assert.equal(byLabel('모두 동의').props.accessibilityState.checked, true);
  await act(() => loginTree.root.find((n) => n.type === 'Pressable' && n.props.accessibilityLabel === '[필수] 서비스 이용약관 동의 전문 보기').props.onPress());
  assert.equal(opened.at(-1), 'https://photospot.app/policies/terms.html');
  await act(() => byLabel('모두 동의').props.onPress());
  assert.ok(boxes().every((n) => n.props.accessibilityState.checked === false), '모두 동의를 다시 누르면 전체 해제');
  await act(() => byLabel('모두 동의').props.onPress());
  await act(async () => { loginButtons()[0].props.onPress(); });
  await flush();
  assert.deepEqual(logins, ['google']);
  const consentEvent = events.at(-1);   // vm 컨텍스트에서 만든 객체라 프로토타입이 달라 복사해 비교한다
  assert.equal(consentEvent[0], 'consent_accept', '필수 동의 3개를 모두 받은 로그인만 consent_accept');
  assert.deepEqual({ ...consentEvent[1] }, { terms: true, privacy: true, age: true });
  assert.ok(!events.some(([name]) => name === 'home_first_card'), '빈 결과에는 home_first_card 없음');
  await act(() => loginTree.unmount());

  // --- 홈 소스: 마운트 효과에 locate 호출이 남아 있지 않다 (회귀 방지) -----------------------------------
  const source = fs.readFileSync(path.resolve(__dirname, '../app/home.tsx'), 'utf8');
  assert.ok(!/useEffect\([^]*?void startingPlace\.locate\(\)[^]*?\}, \[startingPlace\]\)/.test(source), 'home.tsx가 마운트 시 locate()를 부르면 안 된다');
  console.log('Location consent tests passed: no GPS on mount, default 종로·북촌, consent sheet before lookup, unsupported region note, beta banner, three required login consents.');
})().catch((e) => { console.error(e); process.exitCode = 1; });
