const assert = require('node:assert/strict');
const { publicHttps, supportEmail, releaseIssues } = require('./release-config.cjs');

for (const url of ['http://api.photospot.app', 'https://', 'https://localhost', 'https://172.16.1.2',
  'https://[::1]', 'https://2130706433', 'https://api.local', 'https://api.example.com',
  'https://user:secret@api.photospot.app', 'https://api.photospot.app/#secret']) {
  assert.equal(publicHttps(url), false, url);
}
assert.equal(publicHttps('https://api.photospot.app/v1'), true);
for (const email of ['', 'support', 'support@localhost', 'support@example.com', 'help@photospot.example', 'noreply@photospot.app', 'no-reply@photospot.app', 'a b@photospot.app']) {
  assert.equal(supportEmail(email), false, email);
}
assert.equal(supportEmail('support@photospot.app'), true);
const env = {
  EXPO_PUBLIC_API_BASE_URL: 'https://api.photospot.app',
  EXPO_PUBLIC_PRIVACY_URL: 'https://photospot.app/policies/privacy.html',
  EXPO_PUBLIC_TERMS_URL: 'https://photospot.app/policies/terms.html',
  EXPO_PUBLIC_LOCATION_TERMS_URL: 'https://photospot.app/policies/location-terms.html',
  EXPO_PUBLIC_ACCOUNT_DELETION_URL: 'https://photospot.app/policies/account-deletion.html',
  EXPO_PUBLIC_SUPPORT_EMAIL: 'support@photospot.app',
  EAS_PROJECT_ID: '7b19549b-85e8-4ac1-b9e8-4e1c59ccad63',
  EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID: 'fixture-web', EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID: 'fixture-ios',
  EXPO_PUBLIC_REVENUECAT_IOS_KEY: 'appl_fixture', EXPO_PUBLIC_REVENUECAT_ANDROID_KEY: 'goog_fixture',
};
const expo = { icon: './assets/icon.png' };
assert.deepEqual(releaseIssues(env, expo, { growth: true }), []);
const broken = { ...env, EXPO_PUBLIC_ACCOUNT_DELETION_URL: '', EAS_PROJECT_ID: '', EXPO_PUBLIC_DEMO: '1',
  EXPO_PUBLIC_REVENUECAT_ANDROID_KEY: 'test_do-not-print', EXPO_PUBLIC_DEV_TOKEN: 'private-do-not-print' };
const errors = releaseIssues(broken, expo);
assert.equal(errors.length, 5);
assert.ok(!errors.join('').includes('do-not-print'));
assert.ok(releaseIssues({}, expo, { growth: true }).length >= 10);
// 위치정보 이용약관과 고객 문의 연락처는 운영 빌드의 필수 항목 (값은 출력하지 않음)
const noLocationTerms = releaseIssues({ ...env, EXPO_PUBLIC_LOCATION_TERMS_URL: '/policies/location-terms.html' }, expo, { growth: true });
assert.equal(noLocationTerms.length, 1);
assert.match(noLocationTerms[0], /LOCATION_TERMS_URL/);
for (const email of ['', 'support@example.com', 'noreply@photospot.app']) {
  const noContact = releaseIssues({ ...env, EXPO_PUBLIC_SUPPORT_EMAIL: email }, expo, { growth: true });
  assert.equal(noContact.length, 1, email);
  assert.match(noContact[0], /SUPPORT_EMAIL/);
  assert.ok(!noContact[0].includes('example.com') && !noContact[0].includes('noreply'));
}
// Naver uses a server-side code exchange; any secret-looking public variable blocks release.
assert.deepEqual(releaseIssues({ ...env, EXPO_PUBLIC_NAVER_CLIENT_ID: 'naver-id' }, expo, { growth: true }), []);
assert.deepEqual(releaseIssues({ ...env, EXPO_PUBLIC_NAVER_CLIENT_ID: 'naver-id', EXPO_PUBLIC_NAVER_REDIRECT_URI: 'https://photospot.app/oauth/naver' }, expo, { growth: true }), []);
const leaked = releaseIssues({ ...env, EXPO_PUBLIC_NAVER_CLIENT_SECRET: 'secret-do-not-print' }, expo, { growth: true });
assert.equal(leaked.length, 1);
assert.ok(!leaked[0].includes('do-not-print'));
assert.equal(releaseIssues({ ...env, EXPO_PUBLIC_NAVER_REDIRECT_URI: 'http://localhost/cb' }, expo, { growth: true }).length, 1);
// EAS config evaluation uses the same guard; bypassing the CLI cannot bypass it.
const original = process.env;
try {
  process.env = { ...env, APP_VARIANT: 'production' };
  const config = { ...require('../app.json').expo, name: 'Config merge check' };
  assert.equal(require('../app.config.js')({ config }).extra.eas.projectId, env.EAS_PROJECT_ID);
  assert.equal(require('../app.config.js')({ config }).name, 'Config merge check');
  process.env.EXPO_PUBLIC_ACCOUNT_DELETION_URL = 'https://localhost';
  assert.throws(() => require('../app.config.js')({ config }), /ACCOUNT_DELETION/);
} finally { process.env = original; }
console.log('Release guard tests passed: unsafe URLs, missing configuration, policy URLs and support contact, secret redaction, EAS enforcement.');
