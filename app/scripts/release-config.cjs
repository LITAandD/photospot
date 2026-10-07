// Shared by EAS config evaluation and local preflight. Never include values in errors.
const { isIP } = require('node:net');

function publicHttps(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/\.$/, '');
    // Production endpoints use DNS names, including instead of encoded/IPv6 local IPs.
    return url.protocol === 'https:' && !url.username && !url.password && !url.hash &&
      !host.includes(':') && !isIP(host) && host.includes('.') &&
      !/(^|\.)(localhost|local|internal|test|invalid|example)$/.test(host) &&
      !/(^|\.)example\.(com|org|net)$/.test(host) && !host.includes('*');
  } catch { return false; }
}

function releaseIssues(env, expo, { growth = false } = {}) {
  const issues = [];
  for (const key of ['EXPO_PUBLIC_API_BASE_URL', 'EXPO_PUBLIC_PRIVACY_URL', 'EXPO_PUBLIC_TERMS_URL', 'EXPO_PUBLIC_ACCOUNT_DELETION_URL']) {
    if (!publicHttps(env[key])) issues.push(`${key}: 실제 공개 HTTPS 주소를 설정하세요`);
  }
  if (['EXPO_PUBLIC_DEMO', 'EXPO_PUBLIC_DEV_LOGIN'].some(key => env[key] && env[key] !== '0')) {
    issues.push('운영 빌드에서는 EXPO_PUBLIC_DEMO와 EXPO_PUBLIC_DEV_LOGIN을 0으로 설정하세요');
  }
  if (env.EXPO_PUBLIC_DEV_TOKEN) issues.push('EXPO_PUBLIC_DEV_TOKEN: 운영 빌드에서 제거하세요');
  const project = env.EAS_PROJECT_ID || expo.extra?.eas?.projectId || '';
  if (!/^[0-9a-f]{8}-[0-9a-f]{4}-[1-8][0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i.test(project)) {
    issues.push('EAS_PROJECT_ID: Expo 프로젝트의 UUID를 설정하세요');
  }
  if (!expo.icon) issues.push('앱 아이콘을 설정하세요');
  if (!env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID && !env.EXPO_PUBLIC_KAKAO_NATIVE_APP_KEY && !env.EXPO_PUBLIC_NAVER_CLIENT_ID) {
    issues.push('Android 로그인 제공자를 하나 이상 설정하세요');
  }
  if (env.EXPO_PUBLIC_GOOGLE_WEB_CLIENT_ID && !env.EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID) {
    issues.push('EXPO_PUBLIC_GOOGLE_IOS_CLIENT_ID: iOS Google 로그인 설정이 필요해요');
  }
  if (env.EXPO_PUBLIC_NAVER_CLIENT_ID && !env.EXPO_PUBLIC_NAVER_CLIENT_SECRET) {
    issues.push('EXPO_PUBLIC_NAVER_CLIENT_SECRET: 네이버 SDK 설정이 필요해요');
  }
  const billing = ['EXPO_PUBLIC_REVENUECAT_IOS_KEY', 'EXPO_PUBLIC_REVENUECAT_ANDROID_KEY'];
  if (growth || billing.some(key => env[key])) {
    billing.forEach((key, index) => {
      if (!env[key]?.startsWith(index === 0 ? 'appl_' : 'goog_')) issues.push(`${key}: 해당 스토어의 공개 SDK 키를 설정하세요`);
    });
  }
  return issues;
}

module.exports = { publicHttps, releaseIssues };
