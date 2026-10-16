// A partial compatibility adapter must not silently receive new callers/APIs
// after an Expo/Metro/Jest update. Re-review and update this baseline explicitly.
const fs = require('node:fs');
const path = require('node:path');
const crypto = require('node:crypto');
const assert = require('node:assert/strict');
const root = path.resolve(__dirname, '..');
const policy = require('../../security/compat-consumers.json');
const expected = policy.files.map(f => f.file).sort();
for (const item of policy.files) {
  const bytes = fs.readFileSync(path.join(root, item.file));
  assert.equal(crypto.createHash('sha256').update(bytes).digest('hex'), item.sha256, `Re-review compatibility consumer: ${item.file}`);
}
const roots = ['@jest/transform', 'jest-haste-map', 'jest-message-util', 'metro-file-map', 'expo/node_modules/@expo/cli'];
const found = [];
function walk(dir) {
  for (const entry of fs.readdirSync(dir, { withFileTypes: true })) {
    if (entry.name === 'node_modules') continue;
    const file = path.join(dir, entry.name);
    if (entry.isDirectory()) walk(file);
    else if (/\.(js|cjs|mjs)$/.test(file) && /require\(["'](?:micromatch|node-forge|@expo\/code-signing-certificates)["']\)/.test(fs.readFileSync(file, 'utf8'))) {
      found.push(path.relative(root, file).replaceAll('\\', '/'));
    }
  }
}
for (const name of roots) {
  const packageRoot = path.join(root, 'node_modules', name);
  const metadata = JSON.parse(fs.readFileSync(path.join(packageRoot, 'package.json')));
  assert.equal(metadata.version, policy.reviewed_versions[metadata.name]);
  walk(packageRoot);
}
assert.deepEqual(found.sort(), expected, 'New imports require compatibility review');
const lock = require('../package-lock.json');
for (const [name, pkg] of Object.entries(lock.packages)) {
  assert.ok(!/registry\.npmjs\.org\/(?:braces|node-forge|micromatch)\//.test(pkg.resolved || ''), `Removed upstream package reappeared: ${name}`);
  assert.ok(!pkg.dependencies?.braces, `New braces dependency: ${name}`);
}
assert.equal(lock.packages['node_modules/node-forge'].link, true);
assert.equal(lock.packages['compat/expo-certificate-reader'].name, '@photospot/expo-certificate-reader');
console.log('Reviewed consumer versions/imports/hashes and removed upstream package identities passed.');
