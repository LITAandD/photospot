const assert = require('node:assert/strict');
const path = require('node:path');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const req = createRequire(path.resolve(__dirname, '../package.json'));
const match = req('picomatch');
const fixture = require('./glob-compat-fixtures.json');
for (const row of fixture.cases) {
  assert.deepEqual(fixture.paths.map(p => match(row.globs, row.options)(p)), row.some, JSON.stringify(row));
}
const calls = ['anymatch', 'jest-util', 'expo/node_modules/@expo/cli', 'expo/node_modules/@expo/metro-config'];
for (const caller of calls) {
  const callerRequire = createRequire(path.resolve(__dirname, '../node_modules', caller, 'package.json'));
  assert.equal(callerRequire('picomatch'), match, caller);
}
const anymatch = req('anymatch');
assert.equal(anymatch(['**/*.ts', '!**/*.test.ts'], 'src/app.ts'), true);
assert.equal(anymatch(['**/*.ts', '!**/*.test.ts'], 'src/app.test.ts'), false);
const { globsToMatcher } = req('jest-util');
const selected = globsToMatcher(['**/*.ts', '!**/*.test.ts', '**/keep.test.ts']);
assert.deepEqual(['src/app.ts', 'src/app.test.ts', 'src/keep.test.ts', '.hidden.ts'].map(selected), [true, false, true, true]);
const cli = path.dirname(req.resolve('expo/node_modules/@expo/cli/package.json'));
const { createGlobFilter } = require(path.join(cli, 'build/src/utils/createFileTransform.js'));
const filter = createGlobFilter(['*/**', '*/ios/.xcode.env'], { ignore: ['**/ios/*.xcworkspace/**'] });
assert.deepEqual(['package/app.js', 'package/.env', 'package/ios/.xcode.env', 'package/ios/App.xcworkspace/file'].map(filter),
  [true, false, true, false]);
const metro = path.resolve(__dirname, '../node_modules/expo/node_modules/@expo/metro-config');
const { _createSideEffectMatcher } = require(path.join(metro, 'build/serializer/sideEffects.js'));
const effect = _createSideEffectMatcher('/project', { sideEffects: ['*.css', './src/setup.js'] });
assert.deepEqual(['src/a.css', 'src/setup.js', 'src/pure.js'].map(effect), [true, true, false]);
const events = [];
const one = match('**/*', { ignore: '**/*.tmp', onResult: r => events.push(r.input) }, true);
assert.equal(one('src/a.tmp'), false);
assert.equal(one('src/a.ts', true).output, 'src/a.ts');
assert.deepEqual(events, ['src/a.tmp', 'src/a.ts']);
assert.equal(match('!**/*.js', {}, true).state.negated, true);
assert.equal(match('!(a)', {}, true).state.negatedExtglob, true);
assert.equal(match('*.ts', { matchBase: true })('src/a.ts'), true);
assert.equal(match('#file')('#file'), true);
assert.equal(match('*')(''), false);
assert.throws(() => match('*', { capture: true }), /Unreviewed/);
assert.equal(match.makeRe, undefined); // Do not reintroduce a RegExp compilation API.
// Single-branch repeated extglobs (GHSA-fc5q-39xc-vjpf), overlapping branches,
// globstar and brace expansion: bounded child process, not an exception to audit.
execFileSync(process.execPath, ['-e', `
  const assert = require('node:assert/strict');
  const match = require(${JSON.stringify(req.resolve('picomatch'))});
  for (const pattern of ['+(*)b', '+(*a)b', '*(a|aa)b', '+(?*a)b']) {
    assert.equal(match(pattern)('a'.repeat(200) + '!'), false);
  }
  assert.equal(match('**/**/**/missing.js')('a/'.repeat(200) + 'actual.ts'), false);
  assert.throws(() => match('{'.repeat(10000) + 'a,b' + '}'.repeat(10000)), SyntaxError);
`], { timeout: 5000, windowsHide: true, stdio: 'pipe' });
console.log('Non-RegExp matcher: frozen compatibility, actual Expo/Jest/watch consumers, ignore and ReDoS regression passed.');
