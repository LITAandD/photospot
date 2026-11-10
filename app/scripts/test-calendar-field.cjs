// 촬영일 달력(S-4): 지난 날짜는 비활성, 이번 달 이전으로는 못 가며, 웹 보조기기용 aria 상태를 낸다.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;

const TODAY = '2026-11-09';
const transpile = (file) => ts.transpileModule(fs.readFileSync(file, 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, jsx: ts.JsxEmit.ReactJSX, target: ts.ScriptTarget.ES2022, esModuleInterop: true },
}).outputText;
function load(relative) {
  const file = path.resolve(__dirname, '..', relative);
  const mod = { exports: {} };
  vm.runInNewContext(transpile(file), { module: mod, exports: mod.exports, Number, String, Date, Array, Object, require(name) {
    if (name === 'react' || name === 'react/jsx-runtime') return require(name);
    if (name === 'react-native') return { ...Object.fromEntries(['Pressable', 'Text', 'View'].map(n => [n, n])), StyleSheet: { create: (s) => s } };
    if (name === '@/api') return { today: () => TODAY };
    if (name === '@/calendar') return load('src/calendar.ts');
    if (name === './ui') return Object.fromEntries(['Body', 'Button', 'Label', 'Muted'].map(n => [n, n]));
    if (name === '@/theme') return { colors: {}, fonts: {} };
    throw new Error(name);
  } }, { filename: file });
  return mod.exports;
}
const { CalendarField } = load('src/components/calendar-field.tsx');

(async () => {
  const picked = [];
  let tree;
  const render = (value) => act(() => { tree = create(React.createElement(CalendarField, { value, onChange: (v) => picked.push(v) })); });
  await render('2026-11-20');
  const byLabel = (label) => tree.root.findAll(n => n.type === 'Pressable' && n.props.accessibilityLabel === label)[0];
  const day = (date) => tree.root.findAll(n => n.type === 'Pressable' && n.props.testID === `calendar-day-${date}`)[0];
  const month = () => tree.root.findAll(n => n.props.testID === 'calendar-month')[0].props.children.join('');
  const toggle = byLabel('촬영일 달력 열기');
  assert.equal(toggle.props['aria-expanded'], false);
  await act(() => { toggle.props.onPress(); });
  assert.equal(byLabel('촬영일 달력 열기').props['aria-expanded'], true);
  assert.equal(month(), '2026년 11월');
  // 지난 날짜: 비활성 + aria 상태 + 눌러도 선택되지 않음
  assert.equal(day('2026-11-08').props.disabled, true);
  assert.equal(day('2026-11-08').props.accessibilityState.disabled, true);
  assert.match(day('2026-11-08').props.accessibilityLabel, /지난 날짜/);
  await act(() => { day('2026-11-08').props.onPress(); });
  assert.deepEqual(picked, []);
  // 오늘·미래는 고를 수 있고 선택 상태는 aria-selected 로 드러난다
  assert.equal(day('2026-11-09').props.disabled, false);
  assert.equal(day('2026-11-20').props['aria-selected'], true);
  assert.equal(day('2026-11-21').props['aria-selected'], false);
  // 이번 달에서는 '이전 달'이 비활성, 다음 달로 가면 다시 활성
  assert.equal(byLabel('이전 달').props.disabled, true);
  await act(() => { byLabel('다음 달').props.onPress(); });
  assert.equal(month(), '2026년 12월');
  assert.equal(byLabel('이전 달').props.disabled, false);
  assert.equal(day('2026-12-01').props.disabled, false);
  await act(() => { byLabel('이전 달').props.onPress(); });
  assert.equal(month(), '2026년 11월');
  assert.equal(byLabel('이전 달').props.disabled, true);
  await act(() => { day('2026-11-30').props.onPress(); });
  assert.deepEqual(picked, ['2026-11-30']);
  await act(() => tree.unmount());
  // 과거 값이 들어와도 달력은 이번 달부터 보여 준다 ('오늘 선택'으로 되돌릴 수 있다)
  await render('2026-09-01');
  await act(() => { byLabel('촬영일 달력 열기').props.onPress(); });
  assert.equal(month(), '2026년 11월');
  assert.equal(byLabel('이전 달').props.disabled, true);
  await act(() => { tree.root.findAll(n => n.type === 'Button' && n.props.title === '오늘 선택')[0].props.onPress(); });
  assert.deepEqual(picked, ['2026-11-30', TODAY]);
  await act(() => tree.unmount());
  console.log('Calendar field: past days disabled, previous-month arrow stops at the current month, aria-expanded/selected emitted.');
})().catch((e) => { console.error(e); process.exitCode = 1; });
