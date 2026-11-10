const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function load(name) {
  const file = path.resolve(__dirname, '../src', name + '.ts');
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(output, { module: mod, exports: mod.exports, Math, Number });
  return mod.exports;
}
const regions = load('recommendation-regions');
const { RECOMMENDATION_REGIONS, ALL_AREAS, IMPORT_REGIONS, SUPPORTED_REGIONS, DEFAULT_PHOTO_READY_AREA,
  nearestSupportedPreset, importRegionFor, distanceKm } = regions;

// Jeju presets exist; every preset carries an explicit photoReady flag and unique id.
assert.equal(RECOMMENDATION_REGIONS.map(r => r.name).join(','), '서울,부산,강릉,제주');
assert.equal(RECOMMENDATION_REGIONS.find(r => r.name === '제주').areas.map(a => a.name).join(','), '제주시,애월,서귀포,성산');
assert.equal(new Set(ALL_AREAS.map(a => a.id)).size, ALL_AREAS.length);
assert.ok(ALL_AREAS.every(a => typeof a.photoReady === 'boolean' && Number.isFinite(a.lat) && Number.isFinite(a.lng)));
assert.equal(ALL_AREAS.filter(a => a.photoReady).map(a => a.id).join(','), 'seoul-jongno,seoul-seongsu,seoul-hongdae,seoul-yeouido,seoul-namsan');
assert.equal(DEFAULT_PHOTO_READY_AREA.id, 'seoul-jongno');
assert.equal(SUPPORTED_REGIONS, '서울·부산·강릉·제주 일부');

// Import radii mirror pipeline/place_catalog.REGIONS.
assert.equal(IMPORT_REGIONS.map(r => r.key + ':' + r.radiusKm).join(','), 'seoul:18,busan:18,jeju:20,gangneung:15');
assert.ok(Math.abs(distanceKm({ lat: 37.5796, lng: 126.977 }, { lat: 37.4979, lng: 127.0276 }) - 10.1) < 0.3);

// Inside a collected region → nearest preset; outside every radius → null.
assert.equal(nearestSupportedPreset(37.4979, 127.0276).id, 'seoul-gangnam');      // 강남역
assert.equal(nearestSupportedPreset(35.1509, 129.1191).id, 'busan-gwangalli');
assert.equal(nearestSupportedPreset(33.49, 126.45).id, 'jeju-city');
assert.equal(importRegionFor(33.4996, 126.5312).key, 'jeju');
for (const [lat, lng] of [[35.8714, 128.6014], [35.8242, 127.1480], [33.2541, 126.5601], [33.4587, 126.9424], [NaN, 127], [51, 0]]) {
  assert.equal(nearestSupportedPreset(lat, lng), null);                           // 대구·전주·서귀포·성산·invalid·London
  assert.equal(importRegionFor(lat, lng), null);
}
// Presets outside the collected radius are labelled as not ready.
for (const id of ['jeju-seogwipo', 'jeju-seongsan']) {
  const area = ALL_AREAS.find(a => a.id === id);
  assert.equal(area.photoReady, false);
  assert.match(area.description, /준비 중/);
  assert.equal(importRegionFor(area.lat, area.lng), null);
}
console.log('recommendation-regions ok');
