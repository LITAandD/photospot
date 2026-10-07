import assert from 'node:assert/strict';
import test from 'node:test';
import { googleMapUrl, naverMapUrl } from '../dist/index.js';

test('Naver search uses only the place name even if an old address URL exists', () => {
  const name = '사비나 미술관';
  const address = '서울특별시 종로구 율곡로 49-4';
  const old = 'https://map.naver.com/p/search/' + encodeURIComponent(address);
  const url = new URL(naverMapUrl(name, old));
  assert.equal(decodeURIComponent(url.pathname.replace('/p/search/', '')), name);
  assert.equal(naverMapUrl('  스타벅스  여의도IFC몰(L1)R점  ', 'https://map.naver.com/p/entry/place/1084352932'),
    'https://map.naver.com/p/search/' + encodeURIComponent('스타벅스 여의도IFC몰(L1)R점'));
});

test('Google Maps search preserves a Korean place name without sending profile or location data', () => {
  const url = new URL(googleMapUrl('  국립현대미술관  서울관  '));
  assert.equal(url.origin + url.pathname, 'https://www.google.com/maps/search/');
  assert.deepEqual([...url.searchParams], [['api', '1'], ['query', '국립현대미술관 서울관']]);
  for (const name of [null, undefined, '', '   ']) assert.equal(googleMapUrl(name), null);
});

test('Missing names use only a verified direct place page, never a legacy search or empty query', () => {
  assert.equal(naverMapUrl(null, 'https://map.naver.com/p/entry/place/1084352932?old=1'), 'https://map.naver.com/p/entry/place/1084352932');
  assert.equal(naverMapUrl('', 'https://pcmap.place.naver.com/restaurant/1084352932/home'), 'https://pcmap.place.naver.com/restaurant/1084352932/home');
  for (const url of [undefined, 'https://map.naver.com/p/search/OldName', 'http://map.naver.com/p/entry/place/1',
    'https://map.naver.com.evil.test/p/entry/place/1', 'javascript:alert(1)']) {
    assert.equal(naverMapUrl('  ', url), null);
  }
});
