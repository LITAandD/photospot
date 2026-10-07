const assert = require('node:assert/strict');
const { publicHttps, releaseIssues } = require('./release-config.cjs');

for (const url of ['http://api.photospot.app', 'https://', 'https://localhost', 'https://172.16.1.2',
  'https://[::1]', 'https://2130706433', 'https://api.local', 'https://api.example.com',
  'https://user:secret@api.photospot.app', 'https://api.photospot.app/#secret']) {
  assert.equal(publicHttps(url), false, url);
}
assert.equal(publicHttps('https://api.photospot.app/v1'), true);
const env = {
  EXPO_PUBLIC_API_BASE_URL: 'https://api.photospot.app',
  EXPO_PUBLIC_PRIVACY_URL: 'https://photospot.app/privacy',
  EXPO_PUBLIC_TERMS_URL: 'https://photospot.app/terms',
  EXPO_PUBLIC_ACCOUNT_DELETION_URL: 'https://photospot.app/delete',
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
assert.ok(releaseIssues({}, expo, { growth: true }).length >= 8);
// EAS config evaluation uses the same guard; bypassing the CLI cannot bypass it.
const original = process.env;
try {
  process.env = { ...env, APP_VARIANT: 'production' };
  assert.equal(require('../app.config.js')().extra.eas.projectId, env.EAS_PROJECT_ID);
  process.env.EXPO_PUBLIC_ACCOUNT_DELETION_URL = 'https://localhost';
  assert.throws(() => require('../app.config.js')(), /ACCOUNT_DELETION/);
} finally { process.env = original; }
console.log('Release guard tests passed: unsafe URLs, missing configuration, secret redaction, EAS enforcement.');
