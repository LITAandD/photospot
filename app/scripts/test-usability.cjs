const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const React = require('react');
const { act, create } = require('react-test-renderer');
global.IS_REACT_ACT_ENVIRONMENT = true;
function load(file, modules = {}, globals = {}) {
  const mod = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../src', file), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022, jsx: ts.JsxEmit.React, esModuleInterop: true },
  }).outputText, { module: mod, exports: mod.exports, ...globals, require: name => {
    if (name === 'react') return React;
    if (name in modules) return modules[name];
    throw Error(name);
  }});
  return mod.exports;
}
const summary = load('recommendation-summary.ts');
const item = { place_id: 'x', place_name: '테스트 장소', distance_m: 1000, reasons: [], hours: { closed: true, summary: '목 정기휴무' },
  scoring: { basis: 'photo', score: 60, metrics: [
    { key: 'color', label: '사진 색조', status: 'scored', points: 15 },
    { key: 'body', label: '체형', status: 'pending', points: null },
    { key: 'mbti', label: '공간 분위기', status: 'scored', points: -2 },
  ] } };
assert.equal(summary.recommendationSummary(item).reason, '사진 색조 · 입력한 취향과 잘 맞아요');
assert.equal(summary.recommendationSummary(item).evidence, '평가 2/3항목 · 사진 분석 반영');
assert.match(summary.recommendationSummary({ ...item, scoring: null }).reason, /둘러볼/);
const { PlaceRecommendation } = load('components/place-recommendation.tsx', {
  'react-native': { Pressable: 'Pressable', Text: 'Text', View: 'View', useWindowDimensions: () => ({ width: 390 }) },
  '@/theme': { colors: {}, fonts: {} }, '@/recommendation-summary': summary,
  '@/components/place-photo': { PlacePhoto: 'PlacePhoto' }, '@/components/recommendation-badge': { RecommendationBadge: 'Badge' },
});
let tree;
act(() => { tree = create(React.createElement(PlaceRecommendation, { item, onPress() {} })); });
assert.ok(JSON.stringify(tree.toJSON()).includes('선택일 휴무'));
assert.ok(!JSON.stringify(tree.toJSON()).includes('오늘 휴무'));
assert.equal(tree.root.findByType('PlacePhoto').props.style.aspectRatio, 1);
act(() => tree.unmount());

let callback, onVisibility, timer = null, disconnected = 0;
const sent = [], doc = { visibilityState: 'visible', addEventListener: (_, fn) => { onVisibility = fn; }, removeEventListener() {} };
class Observer { constructor(cb) { callback = cb; } observe() {} disconnect() { disconnected++; } }
const { CardExposure } = load('components/card-exposure.web.tsx', {
  'react-native': { View: 'View' }, '@/analytics': { track: async (...args) => { sent.push(args); return true; } },
}, { document: doc, IntersectionObserver: Observer, setTimeout: fn => { timer = fn; return 1; }, clearTimeout: () => { timer = null; } });
act(() => { tree = create(React.createElement(CardExposure, { placeId: 'x', requestId: 'request_1', rank: 1 }, 'card'), { createNodeMock: () => ({}) }); });
callback([{ intersectionRatio: 0.49 }]); assert.equal(timer, null); assert.equal(sent.length, 0);
callback([{ intersectionRatio: 0.6 }]); assert.equal(typeof timer, 'function');
callback([{ intersectionRatio: 0.1 }]); assert.equal(timer, null, 'scroll out cancels dwell');
callback([{ intersectionRatio: 1 }]); doc.visibilityState = 'hidden'; onVisibility(); assert.equal(timer, null);
doc.visibilityState = 'visible'; onVisibility(); timer(); assert.equal(sent.length, 1);
callback([{ intersectionRatio: 1 }]); assert.equal(timer, null, 'same request/place is not repeated');
act(() => tree.update(React.createElement(CardExposure, { placeId: 'x', requestId: 'request_2', rank: 1 }, 'card')));
callback([{ intersectionRatio: 1 }]); timer(); assert.equal(sent.length, 2);
assert.equal(sent[1][1].request_id, 'request_2');
act(() => tree.update(React.createElement(CardExposure, { placeId: 'x', requestId: 'request_3', rank: 1 }, 'card')));
callback([{ intersectionRatio: 1 }]);
act(() => tree.update(React.createElement(CardExposure, { placeId: 'x', requestId: 'request_3', rank: 1, active: false }, 'card')));
assert.equal(timer, null, 'covering modal cancels the impression');
act(() => tree.unmount()); assert.ok(disconnected >= 2);
// A Saju card must carry the same request ID from exposure into detail/save navigation.
const navigations = [];
const { default: Saju } = load('../app/saju.tsx', {
  '@/analytics': { measuredRecommendations: fn => fn() },
  '@/components/card-exposure': { CardExposure: 'CardExposure' },
  'expo-router': { useLocalSearchParams: () => ({ date: '2026-11-12' }), useRouter: () => ({ push: v => navigations.push(v), setParams() {} }) },
  'react-native': { ActivityIndicator: 'ActivityIndicator', Linking: {}, Pressable: 'Pressable', Text: 'Text', View: 'View' },
  '@/api': { api: {}, today: () => '2026-11-12' },
  '@/components/ui': Object.fromEntries(['Body', 'Button', 'Card', 'ErrorBox', 'Muted', 'Screen', 'Title'].map(k => [k, k])),
  '@/components/shoot-plan': { ShootPlan: 'ShootPlan' },
  '@/components/place-recommendation': { PlaceRecommendation: 'PlaceRecommendation' },
  '@/components/start-over': { StartOver: 'StartOver' },
  '@/hooks': { useRefocus() {}, useAsync: () => ({ data: { analytics_request_id: 'saju_request', daily: { deficient_labels: [] }, items: [item] } }) },
  '@/theme': { colors: {}, fonts: {} },
  '@/place-groups': { PLACE_GROUPS: [], placeGroupLabel: () => '전체' },
});
act(() => { tree = create(React.createElement(Saju)); });
act(() => tree.root.findByType('ShootPlan').props.onApply('2026-11-12'));
const exposureId = tree.root.findByType('CardExposure').props.requestId;
act(() => tree.root.findByType('PlaceRecommendation').props.onPress());
assert.equal(exposureId, 'saju_request');
assert.equal(navigations[0].params.request, exposureId);
assert.equal(navigations[0].params.id, item.place_id);
act(() => tree.unmount());
console.log('Usability: evidence-based card reason, selected-day closure, square photo, real exposure threshold/dwell/dedup/background cleanup pass.');
