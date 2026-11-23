// Uncompressed web export budget. Source maps are developer artifacts, not initial assets.
// Baseline main 3ba7a38: photography 337,970 B; complete web export ~2.30 MB.
const fs = require('node:fs');
const path = require('node:path');
const LIMITS = { photography: 400 * 1024, web: 2.5 * 1024 * 1024, asset: 400 * 1024 };
function files(root) {
  if (!fs.existsSync(root)) return [];
  return fs.readdirSync(root, { withFileTypes: true }).flatMap(entry => {
    const file = path.join(root, entry.name);
    return entry.isDirectory() ? files(file) : [{ path: file, bytes: fs.statSync(file).size }];
  });
}
function inspect(appRoot) {
  const photos = files(path.join(appRoot, 'assets/photography'));
  const dist = path.join(appRoot, 'dist');
  const exported = files(dist).filter(file => {
    const relative = path.relative(dist, file.path).replaceAll('\\', '/');
    return !relative.endsWith('.map') && (!relative.startsWith('_expo/') || relative.startsWith('_expo/static/js/web/'));
  });
  const stats = { photography: photos.reduce((n, f) => n + f.bytes, 0), web: exported.reduce((n, f) => n + f.bytes, 0) };
  const issues = [];
  if (!fs.existsSync(path.join(dist, 'index.html'))) issues.push('Web export index.html is missing');
  for (const key of ['photography', 'web']) if (stats[key] > LIMITS[key]) issues.push(`${key}: ${stats[key]} B > ${LIMITS[key]} B`);
  for (const file of exported) if (!file.path.endsWith('.js') && file.bytes > LIMITS.asset)
    issues.push(`${path.relative(dist, file.path)}: ${file.bytes} B > ${LIMITS.asset} B`);
  return { stats, issues };
}
function check(appRoot) {
  const result = inspect(appRoot);
  if (result.issues.length) throw new Error(result.issues.join('\n'));
  console.log('Web asset budget:', JSON.stringify(result.stats));
  return result.stats;
}
module.exports = { inspect, check, LIMITS };
if (require.main === module) check(path.resolve(__dirname, '..'));
