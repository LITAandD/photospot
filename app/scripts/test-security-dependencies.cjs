const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const appRequire = createRequire(path.resolve(__dirname, '../package.json'));
const queryRequire = createRequire(appRequire.resolve('query-string'));
const query = queryRequire('./index.js');
const decode = queryRequire('decode-uri-component');
assert.equal(decode, appRequire('decode-uri-component-upstream').default);
assert.equal(typeof decode, 'function', 'query-string needs a CommonJS callable, not an ESM namespace');
assert.deepEqual({ ...query.parse('label=%EC%84%9C%EC%9A%B8+%EC%88%B2&emoji=%F0%9F%93%B7&tag=a&tag=b&empty=&flag&plus=%2B') },
  { label: '서울 숲', emoji: '📷', tag: ['a', 'b'], empty: '', flag: null, plus: '+' });
const params = { date: '2026-10-16', label: '성수·서울숲', rec: '4931', saju: '0', spot: '', tag: ['카페', '공원'] };
assert.deepEqual({ ...query.parse(query.stringify(params, { sort: false })) }, params);
assert.deepEqual({ ...query.parse('tag=one%2Ctwo', { arrayFormat: 'comma' }) }, { tag: ['one', 'two'] });
assert.deepEqual({ ...query.parse('label=%EC%84%9C%EC%9A%B8+%2B', { decode: false }) }, { label: '%EC%84%9C%EC%9A%B8+%2B' });
assert.equal(decode('%E0%A4%A'), '%E0%A4%A');
assert.equal(decode('%FE%FF'), '\uFFFD\uFFFD');
assert.throws(() => decode(null), TypeError);

// Run the malformed-input regression in a process with a hard deadline so a
// future decoder regression cannot hang the entire CI worker.
execFileSync(process.execPath, ['-e', `
  const assert = require('node:assert/strict');
  const q = require(${JSON.stringify(appRequire.resolve('query-string'))});
  const input = '%FF%80'.repeat(10000);
  assert.equal(q.parse('bad=' + input).bad, input);
  assert.equal(q.parse('bad=%ED%95%9C' + input).bad, '한' + input);
`], { timeout: 5000, stdio: 'pipe', windowsHide: true });

const xcodeRequire = createRequire(appRequire.resolve('xcode'));
const uuid = xcodeRequire('uuid');
assert.equal(xcodeRequire('uuid/package.json').version, '11.1.1');
const project = appRequire('xcode').project('test-only.pbxproj');
project.hash = { project: { objects: { PBXFileReference: {} } } };
const identifiers = new Set();
for (let i = 0; i < 1000; i++) {
  const id = project.generateUuid();
  assert.match(id, /^[A-F0-9]{24}$/);
  assert.ok(!identifiers.has(id));
  identifiers.add(id);
  project.hash.project.objects.PBXFileReference[id] = {};
}
for (const algorithm of [uuid.v3, uuid.v5, uuid.v6]) {
  const small = new Uint8Array(8).fill(0xaa);
  assert.throws(() => algorithm === uuid.v6 ? algorithm({}, small, 4) : algorithm('photo', uuid.v5.DNS, small, 4), RangeError);
  assert.deepEqual(small, new Uint8Array(8).fill(0xaa), 'Invalid output must not partially overwrite a buffer');
}

const nycRequire = createRequire(appRequire.resolve('@istanbuljs/load-nyc-config'));
assert.equal(nycRequire('js-yaml/package.json').version, '4.3.2');
// No hidden older copy may reintroduce the removed advisories on a clean install.
const lock = appRequire('./package-lock.json');
for (const [name, pkg] of Object.entries(lock.packages)) {
  assert.ok(!/(^|\/)node_modules\/sprintf-js$/.test(name), 'sprintf-js must be absent');
  if (/(^|\/)node_modules\/uuid$/.test(name)) assert.equal(pkg.version, '11.1.1');
  if (pkg.name === 'decode-uri-component') assert.equal(pkg.version, '0.5.0');
  if (/(^|\/)node_modules\/decode-uri-component$/.test(name)) assert.equal(pkg.link, true);
}

async function configCompatibility() {
  const parent = fs.realpathSync(os.tmpdir());
  const dir = fs.mkdtempSync(path.join(parent, 'photospot-nyc-'));
  try {
    fs.writeFileSync(path.join(dir, 'package.json'), '{}');
    fs.writeFileSync(path.join(dir, 'shared.yaml'), 'exclude: ["**/*.test.ts"]\nreporter: [text, json]\n');
    fs.writeFileSync(path.join(dir, '.nycrc.yaml'), 'extends: ./shared.yaml\ninclude: &files ["src/**/*.ts"]\nexclude-after-remap: true\ncheck-coverage: true\nlines: 80\n');
    const config = await nycRequire('./index.js').loadNycConfig({ cwd: dir });
    assert.deepEqual(config.include, ['src/**/*.ts']);
    assert.deepEqual(config.exclude, ['**/*.test.ts']);
    assert.deepEqual(config.reporter, ['text', 'json']);
    assert.equal(config.checkCoverage, true);
    assert.equal(config.excludeAfterRemap, true);
    assert.equal(config.lines, 80);
    fs.writeFileSync(path.join(dir, '.nycrc.yaml'), 'include: [unterminated\n');
    await assert.rejects(nycRequire('./index.js').loadNycConfig({ cwd: dir }), /unexpected end/);
  } finally {
    const target = fs.realpathSync(dir);
    assert.equal(path.dirname(target), parent);
    assert.ok(path.basename(target).startsWith('photospot-nyc-'));
    fs.rmSync(target, { recursive: true, force: true });
  }
}
configCompatibility().then(() => console.log('Patched decoder/query-string, bounded malformed input, Xcode UUIDs/buffer checks and NYC YAML configuration passed.'))
  .catch(error => { console.error(error); process.exitCode = 1; });
