const assert = require('node:assert/strict');
const path = require('node:path');
const { createRequire } = require('node:module');
const { execFileSync } = require('node:child_process');
const req = createRequire(path.resolve(__dirname, '../package.json'));
const match = req('micromatch');
const fixture = require('./glob-compat-fixtures.json');
for (const test of fixture.cases) {
  assert.deepEqual(match(fixture.paths, test.globs, test.options), test.list);
  assert.deepEqual(fixture.paths.map(p => match.some(p, test.globs, test.options)), test.some);
}
assert.throws(() => match(['a.js'], '*.ts', { failglob: true }), /No matches/);
assert.deepEqual(match(['a.js'], '*.ts', { nonull: true }), ['*.ts']);
assert.deepEqual(match(['a.js'], '*.ts', { nullglob: true }), ['*.ts']);
assert.equal(match.any('src/test.ts', ['*.js', '**/*.ts']), true);
assert.equal(match.any('src/test.ts', []), false);
assert.equal(match.matcher('**/*.{js,ts}')('src/a.ts'), true);
const events = [];
match(['a.js', 'b.ts'], '*.js', { onResult: result => events.push(result.input) });
assert.deepEqual(events, ['a.js', 'b.ts']);

const metroRoot = path.dirname(req.resolve('metro-file-map/package.json'));
const metro = require(path.join(metroRoot, 'src/watchers/common.js'));
for (const test of fixture.cases) for (let i = 0; i < fixture.paths.length; i++) {
  // Use the actual Metro watcher and its resolved replacement dependency.
  const globs = [].concat(test.globs), dot = !!test.options.dot;
  const expected = globs.length ? match.some(fixture.paths[i], globs, { dot }) : dot || match.some(fixture.paths[i], '**/*');
  assert.equal(metro.includedByGlob('f', globs, dot, fixture.paths[i]), expected);
}
for (const name of ['@jest/transform', 'jest-haste-map', 'jest-message-util', 'metro-file-map']) {
  assert.equal(createRequire(req.resolve(name))('micromatch'), match, `${name} must use the reviewed adapter`);
}
const lock = req('./package-lock.json');
assert.ok(!Object.keys(lock.packages).some(p => /(^|\/)node_modules\/braces$/.test(p)));
assert.ok(!Object.values(lock.packages).some(p => p.dependencies?.braces));
// Bound pathological pattern processing in a child so CI cannot hang.
execFileSync(process.execPath, ['-e', `
  const match = require(${JSON.stringify(req.resolve('micromatch'))});
  for (const n of [100, 1000, 10000]) {
    const glob = '{'.repeat(n) + 'a,b' + '}'.repeat(n);
    try { match.some('a', glob); } catch (e) {
      if (!(e instanceof SyntaxError)) throw e;
    }
  }
`], { timeout: 5000, windowsHide: true, stdio: 'pipe' });
console.log('Picomatch selection/negation/dotfiles/Windows paths, Metro consumers and bounded nested patterns passed.');
