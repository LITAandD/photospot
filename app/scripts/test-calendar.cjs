const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const ts = require('typescript');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(require('node:path').resolve(__dirname, '../src/calendar.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { module: mod, exports: mod.exports });
const { validCalendarDate, calendarMonth, moveCalendarMonth } = mod.exports;
for (const date of ['2024-02-29', '2000-02-29', '2026-12-31', '2027-01-01']) assert.equal(validCalendarDate(date), true);
for (const date of ['2026-02-29', '1900-02-29', '2026-02-31', '2026-13-01', '2026-1-01', '']) assert.equal(validCalendarDate(date), false);
assert.equal(calendarMonth(2024, 1).filter(Boolean).length, 29);
assert.equal(calendarMonth(2026, 1).filter(Boolean).length, 28);
assert.equal(calendarMonth(2026, 9).indexOf('2026-10-01'), 4); // Thursday, independent of host timezone.
assert.equal(calendarMonth(2026, 9).length % 7, 0);
assert.equal(JSON.stringify(moveCalendarMonth(2026, 11, 1)), JSON.stringify({ year: 2027, month: 0 }));
assert.equal(JSON.stringify(moveCalendarMonth(2026, 0, -1)), JSON.stringify({ year: 2025, month: 11 }));
console.log('Calendar tests passed: leap years, invalid dates, weekday placement, year boundaries.');
