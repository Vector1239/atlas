import test from 'node:test';
import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { execFileSync } from 'node:child_process';

test('packaged runtime contains release scripts and skills without personal files or caches', () => {
  const root = fs.mkdtempSync(path.join(os.tmpdir(),'atlas-runtime-test-'));
  try {
    const app = path.join(root,'app');
    const project = path.join(root,'germany-life-hermes');
    fs.mkdirSync(app);
    fs.mkdirSync(path.join(project,'scripts/__pycache__'),{recursive:true});
    fs.mkdirSync(path.join(project,'skills/brief'),{recursive:true});
    fs.mkdirSync(path.join(project,'state'));
    fs.writeFileSync(path.join(project,'scripts/gl_common.py'),'# public runtime');
    fs.writeFileSync(path.join(project,'scripts/germany_life_home.txt'),'/private/location');
    fs.writeFileSync(path.join(project,'scripts/__pycache__/secret.py'),'private cache');
    fs.writeFileSync(path.join(project,'skills/brief/SKILL.md'),'Public skill');
    fs.writeFileSync(path.join(project,'profile.md'),'Private profile');
    fs.writeFileSync(path.join(project,'state/chat.json'),'Private chats');
    fs.copyFileSync(new URL('../build-info.cjs',import.meta.url),path.join(app,'build-info.cjs'));
    execFileSync(process.execPath,[path.join(app,'build-info.cjs')]);
    assert.equal(fs.readFileSync(path.join(app,'runtime/scripts/gl_common.py'),'utf8'),'# public runtime');
    assert.equal(fs.readFileSync(path.join(app,'runtime/skills/brief/SKILL.md'),'utf8'),'Public skill');
    for (const name of ['profile.md','state','scripts/__pycache__','scripts/germany_life_home.txt']) {
      assert.equal(fs.existsSync(path.join(app,'runtime',name)),false,name);
    }
  } finally { fs.rmSync(root,{recursive:true,force:true}); }
});
