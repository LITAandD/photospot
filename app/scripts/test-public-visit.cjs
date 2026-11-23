const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const vm = require('node:vm');
const ts = require('typescript');
const mod = { exports: {} };
vm.runInNewContext(ts.transpileModule(fs.readFileSync(path.join(__dirname, '../src/public-visit.ts'), 'utf8'), {
  compilerOptions: { module: ts.ModuleKind.CommonJS, target: ts.ScriptTarget.ES2022 },
}).outputText, { module: mod, exports: mod.exports });
const { visitHours, admissionLead } = mod.exports;
const hours = { provider: 'official', schedule_kind: 'regular', source_url: 'https://royal.khs.go.kr/ROYAL/contents/R702000000.do', checked_at: '2026-11-12',
  stale: false, closed: false, summary: '월 09:00–17:00 (정규)', notes: ['입장 마감은 관람 종료 1시간 전'] };
assert.equal(visitHours(hours).title, '09:00–17:00');
assert.equal(visitHours(hours).cutoff, '16:00');
assert.equal(visitHours({ ...hours, summary: '월 09:00–18:30 (정규)' }).cutoff, '17:30', 'seasonal hours, not a hardcoded palace deadline');
assert.equal(visitHours({ ...hours, summary: '월 09:00–21:00 (정규)', notes: ['입장 마감 20:00'] }).cutoff, '20:00');
assert.equal(visitHours({ ...hours, summary: '화 정기휴궁 (정규)', closed: true }).status, 'closed');
for (const uncertain of [null, { ...hours, stale: true }, { ...hours, schedule_kind: 'source_text' }]) {
  assert.equal(visitHours(uncertain).status, 'unknown');
  assert.equal(visitHours(uncertain).cutoff, null);
}
assert.equal(visitHours({ ...hours, closed: true, stale: true }).status, 'unknown', 'expired closure is not a verified closure');
assert.equal(visitHours({ ...hours, summary: '월 24시간 개방 (정규)' }).title, '24시간 개방 (정규)');
assert.equal(visitHours({ ...hours, summary: '월 24시간 개방 (정규)' }).status, 'guidance');
for (const overrides of [
  { provider: 'openstreetmap' }, { source_url: '' }, { checked_at: '' },
  { notes: [] }, { notes: ['토요일 입장 마감 16:00'] },
  { notes: ['입장 마감은 관람 종료 1시간 전', '입장 마감 15:30'] },
  { notes: ['입장 마감 08:00'] }, { notes: ['입장 마감 18:00'] },
  { notes: ['입장 마감은 관람 종료 24시간 전'] },
  { summary: '금 22:00–02:00 (정규)' },
  { summary: '월 09:00–17:00 / 야간 19:00–22:00 (특별 일정)' },
]) assert.equal(visitHours({ ...hours, ...overrides }).cutoff, null, JSON.stringify(overrides));
assert.equal(admissionLead('대인 개인 3,000원 (내국인 만 25~64세). 무료 대상은 공식 안내 확인'), '대인 개인 3,000원');
assert.equal(admissionLead('무료. 특별전은 별도 요금'), '무료. 특별전은 별도 요금');
console.log('public visit: closed/unknown/expired, official explicit/seasonal deadlines, ambiguous notes and fees OK');
