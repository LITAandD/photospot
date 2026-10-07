/** Build a public browser demo without loading local environment files. */
const { spawnSync } = require('node:child_process');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const env = {
  ...process.env,
  CI: '1',
  EXPO_NO_DOTENV: '1',
  EXPO_OFFLINE: '1',
  EXPO_PUBLIC_DEMO: '1',
  EXPO_PUBLIC_DEV_LOGIN: '0',
  EXPO_PUBLIC_PREVIEW_API_URL: '',
};

function npm(directory, args) {
  const result = spawnSync('npm', args, {
    cwd: path.join(root, directory), env, stdio: 'inherit',
    shell: process.platform === 'win32', windowsHide: true,
  });
  if (result.error) throw result.error;
  if (result.status !== 0) process.exit(result.status ?? 1);
}

npm('client', ['ci', '--no-audit', '--no-fund']);
npm('client', ['run', 'build']);
npm('app', ['ci', '--no-audit', '--no-fund']);
npm('app', ['exec', '--', 'expo', 'export', '--platform', 'web', '--output-dir', 'dist']);
