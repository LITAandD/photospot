const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const source = fs.readFileSync(path.resolve(__dirname, '../src/web-token-store.ts'), 'utf8');
const code = ts.transpileModule(source, { compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 } }).outputText;
function load(storage) {
  const mod = { exports: {} };
  vm.runInNewContext(code, { module: mod, exports: mod.exports, localStorage: storage });
  return mod.exports.createWebTokenStore;
}
const values = new Map([['photospot.tokens', '{"access":"old","refresh":"old-refresh"}']]);
const storage = { getItem: k => values.get(k), setItem: (k, v) => values.set(k, v), removeItem: k => values.delete(k) };
const create = load(storage), real = create();
assert.equal(values.size, 0); // A previous build's real credentials are removed.
assert.equal(real.get(), null);
const secret = { access: 'real-access', refresh: 'real-refresh' };
real.set(secret);
assert.equal(real.get(), secret);
assert.equal(values.size, 0); // No real token is persisted.
assert.equal(create().get(), null); // Reload means a new authenticated session.
real.clear();
assert.equal(real.get(), null);
const preview = create(true);
preview.set({ access: 'personal-preview-access', refresh: 'personal-preview-refresh' });
assert.equal(create(true).get().access, 'personal-preview-access');
preview.set(secret);
assert.ok(!Array.from(values.values()).some(v => v.includes('real-access')));
values.set('photospot.demo.tokens', JSON.stringify(secret));
assert.equal(create(true).get(), null); // Persisted arbitrary tokens are never trusted.
const blocked = load({ removeItem() { throw Error('blocked'); }, getItem() { throw Error('blocked'); }, setItem() { throw Error('blocked'); } })(true);
blocked.set(secret);
assert.equal(blocked.get(), secret);
blocked.clear();
assert.equal(blocked.get(), null);
console.log('Web credentials: memory-only, legacy cleanup, preview placeholders, blocked storage passed.');
