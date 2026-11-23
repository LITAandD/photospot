const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const crypto = require('node:crypto').webcrypto;
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(require.resolve('../src/visitor-photos.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { module: mod, exports: mod.exports, crypto, process: { env: {} } });
const { freshReceipt, parseReceipt, receiptState } = mod.exports;
const a = freshReceipt(), b = freshReceipt();
assert.match(a.id, /^[\da-f]{8}-[\da-f]{4}-4[\da-f]{3}-[89ab][\da-f]{3}-[\da-f]{12}$/);
assert.match(a.token, /^[\da-f]{64}$/);
assert.notEqual(a.token, b.token);
assert.equal(JSON.stringify(parseReceipt(` ${a.id}.${a.token} `.toUpperCase())), JSON.stringify(a));
assert.equal(parseReceipt(`${a.id}.${a.token.slice(1)}`), null);
assert.equal(parseReceipt(`${a.id}.${a.token}extra`), null);
assert.equal(parseReceipt(''), null);
assert.deepEqual(['pending', 'approved', 'rejected', 'withdrawn'].map(receiptState), ['검수 대기', '공개 중', '미채택', '철회 완료']);
console.log('visitor receipt validation passed');
