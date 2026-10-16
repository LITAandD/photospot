const assert = require('node:assert/strict');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');
const { inventory, checkAudit, runtimeInventory, checkRuntime } = require('../../scripts/check-app-audit.cjs');
const clone = value => JSON.parse(JSON.stringify(value));
const lock = { lockfileVersion: 3, packages: {
  '': { version: '1', dependencies: { tool: '1' } },
  'node_modules/tool': { version: '1', dependencies: { vulnerable: '1' } },
  'node_modules/vulnerable': { version: '1' },
} };
const audit = { auditReportVersion: 2, metadata: { vulnerabilities: { total: 1 } }, vulnerabilities: {
  vulnerable: { nodes: ['node_modules/vulnerable'], via: [{ name: 'vulnerable',
    url: 'https://github.com/advisories/GHSA-abcd-abcd-abcd', severity: 'high', range: '<=1' }] },
} };
const actual = inventory(audit, lock);
const policy = { schema_version: 1, runtime: { vulnerable: { platforms: [], importers: [] } },
  exceptions: actual.map(e => ({ ...e, reviewed_at: '2026-10-16', review_after: '2026-11-16',
    scope: 'build', rationale: 'Reviewed fixture', mitigation: 'Trusted input only' })) };
assert.deepEqual(checkAudit(actual, policy, '2026-10-16'), []);
const changed = clone(audit); changed.vulnerabilities.vulnerable.via[0].url = 'https://github.com/advisories/GHSA-new1-new1-new1';
assert.match(checkAudit(inventory(changed, lock), policy, '2026-10-16').join(), /Unreviewed/); // Same total, different advisory.
const moved = clone(lock); moved.packages[''].dependencies.vulnerable = '1';
assert.match(checkAudit(inventory(audit, moved), policy, '2026-10-16').join(), /path_sha256/);
const upgraded = clone(lock); upgraded.packages['node_modules/vulnerable'].version = '1.1';
assert.match(checkAudit(inventory(audit, upgraded), policy, '2026-10-16').join(), /installations/);
assert.match(checkAudit(actual, policy, '2026-11-16').join(), /Expired/);
const invalidDate = clone(policy); invalidDate.exceptions[0].review_after = '2026-11-31';
assert.match(checkAudit(actual, invalidDate, '2026-10-16').join(), /invalid review/);
const critical = actual.map(e => ({ ...e, severity: 'critical' }));
const criticalPolicy = { ...policy, exceptions: policy.exceptions.map(e => ({ ...e, severity: 'critical' })) };
assert.match(checkAudit(critical, criticalPolicy, '2026-10-16').join(), /cannot be excepted/);
assert.deepEqual(checkAudit(inventory({ ...audit, metadata: { vulnerabilities: { total: 0 } }, vulnerabilities: {} }, lock), policy, '2026-10-16'), []);
assert.throws(() => inventory({ error: { code: 'ENETWORK' } }, lock), /audit response/);
assert.throws(() => inventory({ ...audit, vulnerabilities: {} }, lock), /totals/);
const missing = clone(lock); delete missing.packages['node_modules/vulnerable'];
assert.throws(() => inventory(audit, missing), /absent/);
const cycle = clone(lock); cycle.packages['node_modules/vulnerable'].dependencies = { tool: '1' };
assert.equal(inventory(audit, cycle).length, 1);

// A tooling-only package entering a bundle or a new parse caller blocks release,
// even if the audit total and installed package versions did not change.
const tempRoot = fs.realpathSync(os.tmpdir());
const dir = fs.mkdtempSync(path.join(tempRoot, 'photospot-audit-'));
try {
  const write = (platform, source, content) => {
    const target = path.join(dir, '_expo/static/js', platform);
    fs.mkdirSync(target, { recursive: true });
    fs.writeFileSync(path.join(target, 'entry.js.map'), JSON.stringify({ version: 3, sources: [source], sourcesContent: [content] }));
  };
  for (const p of ['web', 'android', 'ios']) write(p, '../../src/entry.ts', 'export const safe = true;');
  const baseline = runtimeInventory(dir, ['vulnerable']);
  assert.deepEqual(checkRuntime(baseline, policy.runtime), []);
  write('web', '../../node_modules/vulnerable/index.js', 'export const parse = () => {};');
  assert.match(checkRuntime(runtimeInventory(dir, ['vulnerable']), baseline).join(), /platforms/);
  write('web', '../../src/entry.ts', "import decoder from 'vulnerable'; decoder.parse(location.search);");
  assert.match(checkRuntime(runtimeInventory(dir, ['vulnerable']), baseline).join(), /importers/);
  write('web', '../../compat/expo-code-signing/index.cjs', 'module.exports = {};');
  assert.deepEqual(runtimeInventory(dir, ['compat/expo-code-signing'])['compat/expo-code-signing'].platforms, ['web']);
  fs.unlinkSync(path.join(dir, '_expo/static/js/ios/entry.js.map'));
  assert.throws(() => runtimeInventory(dir, ['vulnerable']), /Missing web/);
} finally {
  const target = fs.realpathSync(dir);
  assert.equal(path.dirname(target), tempRoot);
  assert.ok(path.basename(target).startsWith('photospot-audit-'));
  fs.rmSync(target, { recursive: true, force: true });
}
console.log('Audit gate: identity, paths, versions, critical, expiry, malformed reports and runtime drift passed.');
