const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { inspect, check, LIMITS } = require('./web-asset-budget.cjs');
const root = fs.mkdtempSync(path.join(os.tmpdir(), 'photospot-budget-'));
try {
  assert.match(inspect(root).issues[0], /missing/);
  fs.mkdirSync(path.join(root, 'dist'));
  fs.mkdirSync(path.join(root, 'assets/photography'), { recursive: true });
  fs.writeFileSync(path.join(root, 'dist/index.html'), '<html/>');
  assert.equal(check(root).web, 7);
  fs.writeFileSync(path.join(root, 'assets/photography/oversize.webp'), Buffer.alloc(LIMITS.photography + 1));
  assert.throws(() => check(root), /photography/);
  fs.unlinkSync(path.join(root, 'assets/photography/oversize.webp'));
  fs.writeFileSync(path.join(root, 'dist/oversize.png'), Buffer.alloc(LIMITS.asset + 1));
  assert.throws(() => check(root), /oversize.png/);
  fs.unlinkSync(path.join(root, 'dist/oversize.png'));
  fs.mkdirSync(path.join(root, 'dist/_expo/static/js/ios'), { recursive: true });
  fs.writeFileSync(path.join(root, 'dist/_expo/static/js/ios/entry.js'), Buffer.alloc(LIMITS.web + 1));
  assert.equal(inspect(root).issues.length, 0, 'Native output is not a web asset');
  fs.writeFileSync(path.join(root, 'dist/entry.js'), Buffer.alloc(LIMITS.web + 1));
  assert.throws(() => check(root), /web:/);
} finally {
  assert.equal(path.dirname(path.resolve(root)), path.resolve(os.tmpdir()));
  assert.ok(path.basename(root).startsWith('photospot-budget-'));
  fs.rmSync(root, { recursive: true, force: true });
}
console.log('Web asset budgets: missing export and image/total growth blocked.');
