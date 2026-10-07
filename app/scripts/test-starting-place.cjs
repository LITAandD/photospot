const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
function load(name, globals = {}) {
  const file = path.resolve(__dirname, '../src', name + '.ts');
  const output = ts.transpileModule(fs.readFileSync(file, 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText;
  const mod = { exports: {} };
  vm.runInNewContext(output, { module: mod, exports: mod.exports, setTimeout, clearTimeout, Error, ...globals });
  return mod.exports;
}
const { createStartingPlace } = load('starting-place');
const { RECOMMENDATION_REGIONS: regions } = load('recommendation-regions');
const deferred = () => { let resolve; const promise = new Promise(r => { resolve = r; }); return { promise, resolve }; };
(async () => {
  assert.equal(regions.map(r => r.areas.length).join(','), '7,5,3');
  const all = regions.flatMap(r => r.areas);
  assert.equal(new Set(all.map(a => a.id)).size, 15);
  let state;
  const update = next => { state = next; };
  const current = createStartingPlace(async () => ({ lat: 35.1509, lng: 129.1191 }), update);
  await current.locate();
  assert.equal(state.place.id, 'current');
  assert.equal(state.place.lat, 35.1509);

  // A denied / failed lookup must not silently make a Seoul recommendation.
  const denied = createStartingPlace(async () => { throw new Error('권한 거부'); }, update);
  await denied.locate();
  assert.equal(state.place, null);
  assert.equal(state.locating, false);
  assert.equal(state.note, '권한 거부');
  let cancelledCalls = 0;
  const cancelled = createStartingPlace(async () => { cancelledCalls++; return { lat: 37.5, lng: 127 }; }, update);
  const queued = cancelled.locate();
  cancelled.dispose();
  await queued;
  assert.equal(cancelledCalls, 0);
  await createStartingPlace(() => new Promise(() => {}), update, 5).locate();
  assert.equal(state.place, null);
  assert.equal(state.locating, false);
  assert.match(state.note, /시작 장소/);
  await createStartingPlace(async () => ({ lat: 51, lng: 0 }), update).locate();
  assert.equal(state.place, null);
  assert.match(state.note, /국내/);

  // Choosing an area while GPS is waiting must survive its eventual response.
  const pending = deferred();
  const selector = createStartingPlace(() => pending.promise, update);
  const locating = selector.locate();
  selector.select(all[8]);
  pending.resolve({ lat: 37.5796, lng: 126.977 });
  await locating;
  assert.equal(state.place.id, all[8].id);
  assert.equal(state.locating, false);

  // A newer lookup wins even when responses arrive out of order.
  const old = deferred(), fresh = deferred();
  let call = 0;
  const latest = createStartingPlace(() => (++call === 1 ? old.promise : fresh.promise), update);
  const first = latest.locate();
  await Promise.resolve();
  const second = latest.locate();
  fresh.resolve({ lat: 37.7727, lng: 128.9482 });
  old.resolve({ lat: 37.5796, lng: 126.977 });
  await Promise.all([first, second]);
  assert.equal(state.place.lat, 37.7727);
  const unmounted = deferred();
  const disposed = createStartingPlace(() => unmounted.promise, update);
  const gone = disposed.locate();
  disposed.dispose();
  const before = state;
  unmounted.resolve({ lat: 37.5796, lng: 126.977 });
  await gone;
  assert.equal(state, before);

  // Browser adapter asks only once, works without Permissions API, and expires cached fixes.
  let options, calls = 0;
  const web = load('current-location.web', { navigator: { geolocation: {
    getCurrentPosition(success, _error, config) { calls++; options = config; success({ coords: { latitude: 37.5, longitude: 127 } }); },
  } } });
  assert.equal((await web.getCurrentLocation()).lat, 37.5);
  assert.equal(calls, 1);
  assert.equal(options.maximumAge, 60000);
  assert.equal(options.timeout, 10000);
  await assert.rejects(load('current-location.web', { navigator: {} }).getCurrentLocation(), /위치/);
  console.log('Starting place tests passed: GPS, denial, timeout, bounds, manual choice, request races, cleanup, browser support, 15 regions.');
})().catch(error => { console.error(error); process.exitCode = 1; });
