import test from 'node:test';
import assert from 'node:assert/strict';
import { photoAllowsModifications } from '../dist/index.js';

test('ND photos cannot be cropped or overlaid even when the caller requests a square cover', () => {
  for (const photo of [
    {license: 'CC BY-ND 2.0 KR'},
    {license_url: 'https://creativecommons.org/licenses/by-nd/2.0/kr/'},
    {license: '공공누리 3유형'},
    {license: '내용 변경 불가'},
  ]) assert.equal(photoAllowsModifications(photo), false);
});

test('BY/SA images retain the existing composition guide; missing photos remain supported', () => {
  assert.equal(photoAllowsModifications({license: 'CC BY-SA 2.0 KR'}), true);
  assert.equal(photoAllowsModifications({license: 'CC BY 4.0'}), true);
  assert.equal(photoAllowsModifications(), true);
});
