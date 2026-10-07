// Read-only configuration inspection. Does not print credentials or contact providers.
process.env.NODE_ENV = 'production';
require('@expo/env').load(process.cwd(), { silent: true });
const { expo } = require('../app.json');
const { releaseIssues } = require('./release-config.cjs');
const fs = require('node:fs');
const path = require('node:path');
const issues = releaseIssues(process.env, expo, { growth: process.argv.includes('--growth') });
if (expo.icon && !fs.existsSync(path.resolve(__dirname, '..', expo.icon))) issues.push('앱 아이콘 파일을 찾을 수 없어요');
if (issues.length) {
  console.error(`배포 설정: ${issues.length}개 항목 준비 필요\n- ${issues.join('\n- ')}`);
  process.exitCode = 1;
} else {
  console.log('앱 배포 설정 검사 통과. 실제 인증·결제·서명 빌드 및 기기 검증은 별도입니다.');
}
