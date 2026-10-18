import test from 'node:test';
import assert from 'node:assert/strict';
import { createRequire } from 'node:module';

const { translateTexts, batches, setFetch, languageName, isEnglish } = createRequire(import.meta.url)('../browser/translate.cjs');

function fakeService({ expireFirst = false } = {}) {
  const calls = { auth: 0, translate: [] };
  let tokens = 0;
  setFetch(async (url, options = {}) => {
    if (url.startsWith('https://edge.microsoft.com/translate/auth')) {
      calls.auth++;
      return new Response(`token-${++tokens}`);
    }
    assert.match(url, /^https:\/\/api-edge\.cognitive\.microsofttranslator\.com\/translate\?api-version=3\.0&textType=html&to=en$/);
    if (expireFirst && options.headers.Authorization === 'Bearer token-1') return new Response('expired', { status: 401 });
    const body = JSON.parse(options.body);
    calls.translate.push(body.map(item => item.Text));
    return Response.json(body.map(item => ({ detectedLanguage: { language: 'de', score: 1 }, translations: [{ text: `EN:${item.Text}`, to: 'en' }] })));
  });
  return calls;
}

test('texts are translated in order through Edge’s Microsoft Translator service', async () => {
  const calls = fakeService();
  const answers = await translateTexts(['Hauptmarkt', 'Der Markt öffnet am 20. November']);
  assert.deepEqual(answers, [{ text: 'EN:Hauptmarkt', from: 'de' }, { text: 'EN:Der Markt öffnet am 20. November', from: 'de' }]);
  assert.equal(calls.auth, 1);
});

test('repeated text comes from the cache and the sign-in token is reused', async () => {
  const calls = fakeService();
  await translateTexts(['Tickets', 'Anfahrt']);
  const answers = await translateTexts(['Anfahrt', 'Kontakt', 'Tickets']);
  assert.deepEqual(answers.map(answer => answer.text), ['EN:Anfahrt', 'EN:Kontakt', 'EN:Tickets']);
  assert.deepEqual(calls.translate, [['Tickets', 'Anfahrt'], ['Kontakt']]);
  assert.equal(calls.auth, 1);
});

test('an expired sign-in is renewed once', async () => {
  const calls = fakeService({ expireFirst: true });
  const [answer] = await translateTexts(['Veranstaltungen']);
  assert.equal(answer.text, 'EN:Veranstaltungen');
  assert.equal(calls.auth, 2);
});

test('service errors are reported instead of leaving the page half-done silently', async () => {
  setFetch(async url => url.includes('/auth') ? new Response('token') : new Response('busy', { status: 429 }));
  await assert.rejects(translateTexts(['Stadtrat']), /Microsoft Translator answered 429/);
});

test('large pages are split into request-sized batches', () => {
  const many = Array.from({ length: 250 }, (_, i) => `Text ${i}`);
  assert.deepEqual(batches(many).map(group => group.length), [100, 100, 50]);
  const long = ['x'.repeat(5000), 'y'.repeat(5000), 'z'];
  assert.deepEqual(batches(long).map(group => group.length), [1, 2]);
});

test('language codes read as names, and English is recognised', () => {
  assert.equal(languageName('de-DE'), 'German');
  assert.equal(languageName('xx'), '');
  assert.equal(isEnglish('en-GB'), true);
  assert.equal(isEnglish('de'), false);
});
