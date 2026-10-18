// Page translation for web tabs, done the way Microsoft Edge does it: the page stays loaded, its
// text is sent to Microsoft Translator (the service behind Edge's translate button) and written back
// in place, on-screen text first, as HTML so sentences keep their context. The page's own scripts never see Atlas's code or the results' source.
const fs = require('node:fs');
const path = require('node:path');

const AUTH = 'https://edge.microsoft.com/translate/auth';
const API = 'https://api-edge.cognitive.microsofttranslator.com/translate';
const WORLD = 1207;
const PAGE_SCRIPT = fs.readFileSync(path.join(__dirname, 'page-translate.js'), 'utf8');
const BATCH_ITEMS = 100, BATCH_CHARS = 9000, PARALLEL = 3, PULL = 400;

let fetcher = (...args) => require('electron').net.fetch(...args);
let token = null;
const cache = new Map();

// Splits texts into request-sized batches, keeping their order.
function batches(texts) {
  const out = [];
  let current = [], size = 0;
  for (const text of texts) {
    if (current.length && (current.length >= BATCH_ITEMS || size + text.length > BATCH_CHARS)) { out.push(current); current = []; size = 0; }
    current.push(text); size += text.length;
  }
  if (current.length) out.push(current);
  return out;
}

async function authToken(fresh = false) {
  if (!fresh && token && token.expires > Date.now()) return token.value;
  const response = await fetcher(AUTH);
  if (!response.ok) throw new Error(`Microsoft Translator sign-in failed (${response.status})`);
  token = { value: (await response.text()).trim(), expires: Date.now() + 8 * 60 * 1000 };
  return token.value;
}

async function request(texts, to, fresh = false) {
  const response = await fetcher(`${API}?api-version=3.0&textType=html&to=${encodeURIComponent(to)}`, {
    method: 'POST',
    headers: { Authorization: `Bearer ${await authToken(fresh)}`, 'Content-Type': 'application/json' },
    body: JSON.stringify(texts.map(text => ({ Text: text })))
  });
  if (response.status === 401 && !fresh) return request(texts, to, true);
  if (!response.ok) throw new Error(`Microsoft Translator answered ${response.status}`);
  const data = await response.json();
  if (!Array.isArray(data) || data.length !== texts.length) throw new Error('Microsoft Translator sent an unexpected answer');
  return data.map(item => ({ text: item?.translations?.[0]?.text ?? '', from: item?.detectedLanguage?.language ?? '' }));
}

// Translates texts to `to`, reusing earlier answers; returns [{ text, from }] in the same order.
async function translateTexts(texts, to = 'en') {
  const results = new Array(texts.length);
  const missing = [];
  texts.forEach((text, index) => {
    const hit = cache.get(`${to}\n${text}`);
    if (hit) results[index] = hit; else missing.push(index);
  });
  for (const group of batches(missing.map(index => texts[index]))) {
    const answers = await translateTexts.engine(group, to);
    group.forEach((text, offset) => {
      const index = missing.shift();
      results[index] = answers[offset];
      if (cache.size > 20000) cache.clear();
      cache.set(`${to}\n${text}`, answers[offset]);
    });
  }
  return results;
}
translateTexts.engine = request;

function setFetch(next) { fetcher = next; token = null; cache.clear(); }

const LANGUAGES = { de: 'German', fr: 'French', nl: 'Dutch', es: 'Spanish', it: 'Italian', pl: 'Polish', cs: 'Czech', da: 'Danish', sv: 'Swedish', nb: 'Norwegian', no: 'Norwegian', pt: 'Portuguese', lb: 'Luxembourgish' };
const languageName = code => LANGUAGES[String(code).toLowerCase().split('-')[0]] || '';
const isEnglish = code => /^en\b/i.test(String(code || ''));

// Keeps one web tab translated: pulls new text as the page changes and restores it on request.
class PageTranslator {
  constructor(contents, onChange) {
    this.contents = contents; this.onChange = onChange;
    this.on = false; this.busy = false; this.from = ''; this.failure = ''; this.timer = null; this.run = 0;
  }

  state() { return { on: this.on, busy: this.busy, from: languageName(this.from) || this.from, failure: this.failure }; }

  async page(code) {
    if (this.contents.isDestroyed()) return null;
    return this.contents.executeJavaScriptInIsolatedWorld(WORLD, [{ code }]).catch(() => null);
  }

  start() {
    this.on = true; this.failure = ''; this.from = '';
    this.schedule(0);
    this.onChange();
  }

  async stop() {
    this.on = false; this.busy = false; this.run++;
    clearTimeout(this.timer);
    await this.page('window.__atlasTranslate && window.__atlasTranslate.restore()');
    this.onChange();
  }

  dispose() { this.on = false; this.run++; clearTimeout(this.timer); }

  // A new document replaces the page's script; keep translating if the tab is still translated.
  navigated() {
    if (!this.on) return;
    this.from = '';
    this.schedule(300);
  }

  schedule(delay) {
    clearTimeout(this.timer);
    if (this.on) this.timer = setTimeout(() => this.pass(this.run), delay);
  }

  async pass(run) {
    if (!this.on || run !== this.run || this.contents.isDestroyed()) return;
    await this.page(PAGE_SCRIPT);
    const dirty = await this.page('window.__atlasTranslate ? window.__atlasTranslate.dirty() : true');
    if (!dirty) return this.schedule(1000);
    const items = await this.page(`window.__atlasTranslate ? window.__atlasTranslate.collect(${PULL}) : []`) || [];
    if (!items.length) { if (this.busy) { this.busy = false; this.onChange(); } return this.schedule(1000); }
    if (!this.busy) { this.busy = true; this.onChange(); }
    const groups = batches(items.map(item => item.text)).map(texts => items.splice(0, texts.length));
    let failed = null;
    const work = groups.slice();
    const lanes = Array.from({ length: Math.min(PARALLEL, work.length) }, async () => {
      for (let group = work.shift(); group && !failed; group = work.shift()) {
        try {
          const answers = await translateTexts(group.map(item => item.text));
          if (run !== this.run) return;
          const from = answers.find(answer => answer.from)?.from;
          if (from && !this.from) { this.from = from; this.onChange(); }
          await this.page(`window.__atlasTranslate && window.__atlasTranslate.apply(${JSON.stringify(group.map((item, i) => ({ id: item.id, text: answers[i].text })))})`);
        } catch (error) {
          failed = error;
          await this.page(`window.__atlasTranslate && window.__atlasTranslate.release(${JSON.stringify(group.map(item => item.id))})`);
        }
      }
    });
    await Promise.all(lanes);
    if (run !== this.run) return;
    if (failed) {
      this.failure = `Translation failed: ${failed.message}`;
      return this.stop();
    }
    this.schedule(0);
  }
}

module.exports = { translateTexts, batches, setFetch, PageTranslator, languageName, isEnglish };
