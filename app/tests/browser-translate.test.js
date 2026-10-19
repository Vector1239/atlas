import test from 'node:test';
import assert from 'node:assert/strict';
import crypto from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { createRequire } from 'node:module';

const require = createRequire(import.meta.url);
const { translateTexts, batches, detectLanguage, languageName, isEnglish } = require('../browser/translate.cjs');
const local = require('../browser/local-translator.cjs');

const sha = text => crypto.createHash('sha256').update(text).digest('hex');
const REGISTRY = 'https://storage.googleapis.com/bergamot-models-sandbox/0.3.3/';

function fakeRegistry(folder, { badModel = false } = {}) {
  const files = { model: 'model.deen.bin', lex: 'lex.deen.bin', vocab: 'vocab.deen.spm' };
  const body = name => `contents of ${name}`;
  const registry = { deen: Object.fromEntries(Object.entries(files).map(([part, name]) => [part, { name, expectedSha256Hash: sha(body(name)) }])), ende: {} };
  const requests = [];
  local.configure({ folder, fetch: async url => {
    requests.push(url.replace(REGISTRY, ''));
    if (url === `${REGISTRY}registry.json`) return Response.json(registry);
    const name = url.split('/').pop();
    return new Response(badModel && name.startsWith('model') ? 'tampered' : body(name));
  } });
  return requests;
}

test('a language model downloads once, is checked, and is read from disk afterwards', async () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-models-'));
  try {
    const requests = fakeRegistry(folder);
    let downloads = 0;
    const buffers = await local.loadModel('de', () => downloads++);
    assert.equal(Buffer.from(buffers.model).toString(), 'contents of model.deen.bin');
    assert.equal(buffers.vocabs.length, 1);
    assert.equal(downloads, 1);
    assert.deepEqual(await local.sourceLanguages(), ['de']);
    assert.ok(fs.existsSync(path.join(folder, 'deen', 'model.deen.bin')));

    const again = fakeRegistry(folder);
    await local.loadModel('de', () => downloads++);
    assert.equal(downloads, 1);
    assert.deepEqual(again, ['registry.json']);
    assert.ok(requests.includes('deen/model.deen.bin'));
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
});

test('a model file that fails its checksum is refused and not kept', async () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-models-'));
  try {
    fakeRegistry(folder, { badModel: true });
    await assert.rejects(local.loadModel('de'), /failed its checksum/);
    assert.equal(fs.existsSync(path.join(folder, 'deen', 'model.deen.bin')), false);
    await assert.rejects(local.loadModel('xx'), /no on-device model/);
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
});

test('the language list still loads offline from the saved copy', async () => {
  const folder = fs.mkdtempSync(path.join(os.tmpdir(), 'atlas-models-'));
  try {
    fakeRegistry(folder);
    await local.sourceLanguages();
    local.configure({ folder, fetch: async () => { throw new Error('offline'); } });
    assert.deepEqual(await local.sourceLanguages(), ['de']);
  } finally { fs.rmSync(folder, { recursive: true, force: true }); }
});

test('repeated text is translated once and comes back in order', async () => {
  const calls = [];
  const engine = translateTexts.engine;
  translateTexts.engine = async (texts, from) => { calls.push([from, ...texts]); return texts.map(text => `EN:${text}`); };
  try {
    assert.deepEqual(await translateTexts(['Tickets', 'Anfahrt'], 'de'), ['EN:Tickets', 'EN:Anfahrt']);
    assert.deepEqual(await translateTexts(['Anfahrt', 'Kontakt', 'Tickets'], 'de'), ['EN:Anfahrt', 'EN:Kontakt', 'EN:Tickets']);
    assert.deepEqual(calls, [['de', 'Tickets', 'Anfahrt'], ['de', 'Kontakt']]);
  } finally { translateTexts.engine = engine; }
});

test('pages are split into small batches so on-screen text lands first', () => {
  const many = Array.from({ length: 50 }, (_, i) => `Text ${i}`);
  assert.deepEqual(batches(many).map(group => group.length), [24, 24, 2]);
  assert.deepEqual(batches(['x'.repeat(3000), 'y'.repeat(3000), 'z']).map(group => group.length), [1, 2]);
});

test('a page’s language is recognised from its words when it doesn’t declare one', () => {
  assert.equal(detectLanguage(['Der Markt öffnet am 20. November auf dem Hauptmarkt und ist bis Weihnachten für alle da.']), 'de');
  assert.equal(detectLanguage(['<span id="t0">Le marché ouvre </span><span id="t1">le 20 novembre</span> sur la place et est pour tous.']), 'fr');
  assert.equal(detectLanguage(['De markt opent op 20 november en is voor iedereen met de kinderen.']), 'nl');
  assert.equal(detectLanguage(['The market opens on 20 November and is open to everyone in the town.']), 'en');
  assert.equal(detectLanguage(['Tickets']), '');
});

test('language codes read as names, and English is recognised', () => {
  assert.equal(languageName('de-DE'), 'German');
  assert.equal(languageName('xx'), '');
  assert.equal(isEnglish('en-GB'), true);
  assert.equal(isEnglish('de'), false);
});
