const assert = require('node:assert/strict');
const fs = require('node:fs'), path = require('node:path'), vm = require('node:vm'), ts = require('typescript');
const storage = new Map();
let intended = null;
function load() {
  const mod = { exports: {} };
  vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.resolve(__dirname, '../src/browse-context.ts'), 'utf8'), {
    compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
  }).outputText, { module: mod, exports: mod.exports, sessionStorage: { getItem: k => storage.get(k), setItem: (k, v) => storage.set(k, v), removeItem: k => storage.delete(k) },
    require: name => name === './recommendation-regions' ? { ALL_AREAS: [{ id: 'busan-haeundae', lat: 35.1587 }] } : {
      clearIntendedRoute: () => { intended = null; }, peekIntendedRoute: () => intended, rememberIntendedRoute: v => { intended = v; },
    } });
  return mod.exports;
}
let c = load();
assert.equal(c.browseDate('2026-02-31', 'fallback'), 'fallback');
assert.equal(c.browseContext({ city: '__proto__' }, '2026-11-12'), null);
const context = c.browseContext({ city: 'busan', date: '2026-11-19', place: '11111111-2222-3333-4444-555555555555' }, '');
assert.equal(c.browseArea(context.city).lat, 35.1587);
c.beginBrowseCustomization(context);
assert.equal(intended, '/home?city=busan&date=2026-11-19&place=11111111-2222-3333-4444-555555555555');
c = load(); // reload a tab: no module memory, but the context survives
assert.equal(c.pendingBrowse().place, context.place);
assert.equal(c.browseHref(context).pathname, '/browse/[id]');
assert.equal(c.browseHref(context, false).pathname, '/browse');
c.clearBrowseCustomization(true);
assert.equal(intended, null);
assert.equal(c.pendingBrowse(), null);
storage.set('photospot.browse.customization', JSON.stringify({ context, at: Date.now() - 7200001 }));
assert.equal(c.pendingBrowse(), null);
storage.set('photospot.browse.customization', JSON.stringify({ context: null, at: Date.now() }));
assert.equal(c.pendingBrowse(), null);
storage.set('photospot.browse.customization', JSON.stringify({ context: { city: 'busan', date: 'bad' }, at: Date.now() }));
assert.equal(c.pendingBrowse(), null);
console.log('Browse context: validated city/date/UUID, tab reload, cancellation and expiry pass.');
