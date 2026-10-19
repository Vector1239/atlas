// Page translation for web tabs. The page stays loaded: its text is translated on this Mac by the
// on-device translator in local-translator.cjs and written back in place, on-screen text first, as
// HTML so sentences keep their context. The page's own scripts never see Atlas's code.
const fs = require('node:fs');
const path = require('node:path');
const local = require('./local-translator.cjs');

const WORLD = 1207;
const PAGE_SCRIPT = fs.readFileSync(path.join(__dirname, 'page-translate.js'), 'utf8');
const BATCH_ITEMS = 24, BATCH_CHARS = 4000, PULL = 400;
const cache = new Map();

// Splits texts into batches, keeping their order; small batches let on-screen text land first.
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

// Translates HTML snippets from `from` into English, reusing earlier results.
async function translateTexts(texts, from) {
  const results = new Array(texts.length);
  const missing = [];
  texts.forEach((text, index) => {
    const hit = cache.get(`${from}\n${text}`);
    if (hit !== undefined) results[index] = hit; else missing.push(index);
  });
  if (missing.length) {
    const answers = await translateTexts.engine(missing.map(index => texts[index]), from);
    missing.forEach((index, offset) => {
      results[index] = answers[offset];
      if (cache.size > 20000) cache.clear();
      cache.set(`${from}\n${texts[index]}`, answers[offset]);
    });
  }
  return results;
}
translateTexts.engine = local.translate;

const LANGUAGES = { de: 'German', fr: 'French', nl: 'Dutch', es: 'Spanish', it: 'Italian', pl: 'Polish', cs: 'Czech', pt: 'Portuguese', bg: 'Bulgarian', et: 'Estonian', fa: 'Persian', is: 'Icelandic', nb: 'Norwegian', nn: 'Norwegian', ru: 'Russian', uk: 'Ukrainian', lb: 'Luxembourgish', da: 'Danish', sv: 'Swedish', en: 'English' };
const languageName = code => LANGUAGES[String(code).toLowerCase().split('-')[0]] || '';
const isEnglish = code => /^en\b/i.test(String(code || ''));

// Common short words per language; enough to tell what a page is written in when it doesn't say.
const STOPWORDS = {
  en: 'the and of to in is for on with that this are you your from at by be or not have will',
  de: 'der die das und ist nicht mit sich auf für ein eine den dem zu von im auch wir sie werden bei',
  fr: 'le la les et est des une pour dans pas que qui sur avec au du ce sont vous nous par',
  nl: 'de het een en is van niet dat op voor met zijn ook wij u bij naar om te',
  es: 'el la los las y es en del que por una para con no se su al como más',
  it: 'il la di che è e per una non sono con gli del della le nel anche',
  pt: 'o a os as e é de do da que não em para com uma um se por mais',
  pl: 'i w na nie się z do jest to że jak dla od po o są',
  cs: 'a je se na že v do to s pro jsou jako by ale od'
};
const WORDS = Object.fromEntries(Object.entries(STOPWORDS).map(([code, list]) => [code, new Set(list.split(' '))]));

// Guesses the language of some text from its common words; returns '' when there's too little to go on.
function detectLanguage(texts) {
  const words = texts.join(' ').replace(/<[^>]*>/g, ' ').toLowerCase().match(/\p{L}+/gu) || [];
  const scores = Object.fromEntries(Object.keys(WORDS).map(code => [code, 0]));
  for (const word of words.slice(0, 3000)) for (const code in WORDS) if (WORDS[code].has(word)) scores[code]++;
  const [best, score] = Object.entries(scores).sort((a, b) => b[1] - a[1])[0];
  return score >= 3 ? best : '';
}

// Keeps one web tab translated: pulls new text as the page changes and restores it on request.
class PageTranslator {
  constructor(contents, onChange, declaredLanguage = () => '') {
    this.contents = contents; this.onChange = onChange; this.declaredLanguage = declaredLanguage;
    this.on = false; this.busy = false; this.downloading = false;
    this.from = ''; this.failure = ''; this.timer = null; this.run = 0;
  }

  state() {
    return { on: this.on, busy: this.busy, downloading: this.downloading, from: languageName(this.from) || this.from, failure: this.failure };
  }

  async page(code) {
    if (this.contents.isDestroyed()) return null;
    return this.contents.executeJavaScriptInIsolatedWorld(WORLD, [{ code }]).catch(() => null);
  }

  start() {
    this.on = true; this.failure = ''; this.from = '';
    this.schedule(0);
    this.onChange();
  }

  async stop(failure = '') {
    this.on = false; this.busy = false; this.downloading = false; this.failure = failure; this.run++;
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

  // Settles which language the page is in, and makes sure its model is ready.
  async source(items, run) {
    if (this.from) return this.from;
    const declared = String(this.declaredLanguage() || '').toLowerCase().split('-')[0];
    const from = declared && declared !== 'en' && LANGUAGES[declared] ? declared : detectLanguage(items.map(item => item.text)) || declared;
    if (!from) throw new Error('couldn’t tell which language this page is in');
    if (from === 'en') { await this.stop('This page is already in English'); return null; }
    const supported = await local.sourceLanguages();
    if (!supported.includes(from)) throw new Error(`there is no on-device model for ${languageName(from) || from} yet`);
    await local.loadModel(from, () => { this.downloading = true; this.onChange(); });
    if (run !== this.run) return null;
    this.downloading = false;
    this.from = from;
    this.onChange();
    return from;
  }

  async pass(run) {
    if (!this.on || run !== this.run || this.contents.isDestroyed()) return;
    await this.page(PAGE_SCRIPT);
    const dirty = await this.page('window.__atlasTranslate ? window.__atlasTranslate.dirty() : true');
    if (!dirty) return this.schedule(1000);
    const items = await this.page(`window.__atlasTranslate ? window.__atlasTranslate.collect(${PULL}) : []`) || [];
    if (!items.length) { if (this.busy) { this.busy = false; this.onChange(); } return this.schedule(1000); }
    if (!this.busy) { this.busy = true; this.onChange(); }
    const release = list => this.page(`window.__atlasTranslate && window.__atlasTranslate.release(${JSON.stringify(list.map(item => item.id))})`);
    let from;
    try { from = await this.source(items, run); } catch (error) { await release(items); return this.stop(`Translation failed: ${error.message}`); }
    if (!from || run !== this.run) return;
    const work = batches(items.map(item => item.text)).map(texts => items.splice(0, texts.length));
    let failed = null;
    const lanes = Array.from({ length: Math.min(3, work.length) }, async () => {
      for (let group = work.shift(); group && !failed; group = work.shift()) {
        try {
          const answers = await translateTexts(group.map(item => item.text), from);
          if (run !== this.run) return;
          await this.page(`window.__atlasTranslate && window.__atlasTranslate.apply(${JSON.stringify(group.map((item, i) => ({ id: item.id, text: answers[i] })))})`);
        } catch (error) {
          failed = error;
          await release(group);
        }
      }
    });
    await Promise.all(lanes);
    if (run !== this.run) return;
    if (failed) return this.stop(`Translation failed: ${failed.message}`);
    this.schedule(0);
  }
}

module.exports = { translateTexts, batches, detectLanguage, PageTranslator, languageName, isEnglish };
