const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
let revision = null;
try { revision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: __dirname, encoding: 'utf8' }).trim(); } catch {}
fs.writeFileSync(path.join(__dirname, 'build-info.json'), JSON.stringify({ revision }) + '\n');
