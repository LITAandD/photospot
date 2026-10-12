// One entry point used by developers, Makefile and CI.
const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
for (const file of fs.readdirSync(__dirname).filter(f => /^test-.+\.cjs$/.test(f)).sort()) {
  execFileSync(process.execPath, [path.join(__dirname, file)], { stdio: 'inherit' });
}
