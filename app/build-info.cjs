const fs = require('node:fs');
const path = require('node:path');
const { execFileSync } = require('node:child_process');
let revision = null;
try { revision = execFileSync('git', ['rev-parse', 'HEAD'], { cwd: __dirname, encoding: 'utf8', stdio:['ignore','pipe','ignore'] }).trim(); } catch {}
fs.writeFileSync(path.join(__dirname, 'build-info.json'), JSON.stringify({ revision }) + '\n');
// Ship public runtime code with the app; personal files stay in the project folder.
const runtime = path.join(__dirname, 'runtime');
fs.rmSync(runtime, { recursive: true, force: true });
for (const folder of ['scripts', 'skills']) {
  fs.cpSync(path.join(__dirname, '../germany-life-hermes', folder), path.join(runtime, folder), {
    recursive: true,
    filter: source => fs.statSync(source).isDirectory()
      ? path.basename(source) !== '__pycache__'
      : (folder === 'scripts' ? source.endsWith('.py') : path.basename(source) === 'SKILL.md')
  });
}
