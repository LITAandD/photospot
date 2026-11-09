// react-native-web 0.21 은 accessibilityState 를 DOM 에 옮기지 않는다 — 공용 컨트롤이 aria-* 를 함께 내는지 확인한다 (S-3·N-copy-1).
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

// 설치된 RNW 가 accessibilityState 를 그대로 흘리지 않는지(즉 aria-* 가 필요한지) 소스에서 확인한다
const rnw = fs.readFileSync(path.resolve(__dirname, '../node_modules/react-native-web/dist/modules/createDOMProps/index.js'), 'utf8');
assert.equal(rnw.includes('accessibilityState'), false, 'RNW 가 accessibilityState 를 매핑하기 시작했다면 이 테스트와 aria-* 중복을 재검토');
assert.ok(rnw.includes('"aria-checked"') && rnw.includes('"aria-pressed"') && rnw.includes('"aria-busy"'));

const file = path.resolve(__dirname, '../src/components/ui.tsx');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText, { module: mod, exports: mod.exports, Object, Array, Math, Number, require(name) {
  if (name === 'react' || name === 'react/jsx-runtime') return require(name);
  if (name === 'react-native') return { ...Object.fromEntries(['ActivityIndicator', 'Pressable', 'ScrollView', 'Text', 'TextInput', 'View'].map(n => [n, n])), StyleSheet: { create: (s) => s } };
  if (name === 'expo-router') return { useRouter: () => ({}), Link: 'Link', Stack: 'Stack' };
  if (name === 'react-native-safe-area-context') return { useSafeAreaInsets: () => ({ top: 0, bottom: 0, left: 0, right: 0 }) };
  if (name === '@/theme') return { colors: {}, fonts: {}, radius: {} };
  throw new Error(name);
} }, { filename: file });
const { Button, Chip, OptionRow, Toast, Card } = mod.exports;
const render = (el) => { let t; act(() => { t = create(el); }); return t; };
const pressable = (t) => t.root.findByType('Pressable');

// Button: 로딩이면 aria-busy, 비활성은 Pressable 의 disabled (RNW 가 aria-disabled 로 출력)
let t = render(React.createElement(Button, { title: '저장', onPress() {}, loading: true }));
assert.equal(pressable(t).props['aria-busy'], true);
assert.equal(pressable(t).props.disabled, true);
t = render(React.createElement(Button, { title: '저장', onPress() {} }));
assert.equal(pressable(t).props['aria-busy'], false);
assert.ok(!pressable(t).props.disabled);
// Chip: radio 는 aria-checked, button 은 aria-pressed — 둘 다 accessibilityState 도 유지
t = render(React.createElement(Chip, { label: '여성', selected: true, onPress() {}, role: 'radio' }));
assert.equal(pressable(t).props['aria-checked'], true);
assert.equal(pressable(t).props['aria-pressed'], undefined);
assert.equal(JSON.stringify(pressable(t).props.accessibilityState), '{"checked":true}');
t = render(React.createElement(Chip, { label: '5km', selected: false, onPress() {} }));
assert.equal(pressable(t).props['aria-pressed'], false);
assert.equal(pressable(t).props['aria-checked'], undefined);
assert.equal(JSON.stringify(pressable(t).props.accessibilityState), '{"selected":false}');
// OptionRow
t = render(React.createElement(OptionRow, { title: '봄 웜', selected: true, onPress() {} }));
assert.equal(pressable(t).props['aria-pressed'], true);
// Toast: 조용한 상태 알림, 메시지 없으면 렌더하지 않음
t = render(React.createElement(Toast, { message: '복사했어요' }));
assert.equal(t.root.findByType('View').props.role, 'status');
assert.equal(t.root.findByType('View').props['aria-live'], 'polite');
assert.equal(render(React.createElement(Toast, { message: null })).toJSON(), null);
// Card 는 testID 를 넘긴다 (없는 장소 카드 검사용)
t = render(React.createElement(Card, { testID: 'x' }, 'c'));
assert.equal(t.root.findByType('View').props.testID, 'x');
console.log('UI aria: Button aria-busy, Chip aria-checked/aria-pressed, OptionRow aria-pressed, Toast role=status, Card testID.');
