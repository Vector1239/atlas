// On-device translation, the way Firefox and Zen do it: Mozilla's Bergamot translator (WebAssembly)
// runs in worker threads inside Atlas. Each language's model (about 23 MB) is downloaded once from
// the Bergamot model registry, checked against its SHA-256 and kept in Atlas's app data; after that,
// pages translate with no account, no service and nothing leaving the Mac.
const { Worker } = require('node:worker_threads');
const crypto = require('node:crypto');
const fs = require('node:fs');
const os = require('node:os');
const path = require('node:path');

const REGISTRY = 'https://storage.googleapis.com/bergamot-models-sandbox/0.3.3/';
const WORKER_FILE = path.join(path.dirname(require.resolve('@browsermt/bergamot-translator/package.json')), 'worker', 'translator-worker.js');
// The package's worker is CommonJS inside an ES module package, so it is run through a small loader.
const BOOT = `
const { workerData } = require('node:worker_threads');
const source = require('node:fs').readFileSync(workerData.file, 'utf8');
new Function('require', '__filename', '__dirname', source)(require, workerData.file, require('node:path').dirname(workerData.file));
`;

let options = { fetch: (...args) => require('electron').net.fetch(...args), folder: null, workers: Math.max(1, Math.min(3, os.cpus().length - 1)) };
let registry = null, pool = null;
const models = new Map(); // pair -> Promise<buffers>

function configure(next) { Object.assign(options, next); registry = null; models.clear(); }

function folder() {
  return options.folder || path.join(require('electron').app.getPath('userData'), 'translation-models', '0.3.3');
}

async function download(url) {
  const response = await options.fetch(url);
  if (!response.ok) throw new Error(`model download failed (${response.status})`);
  return Buffer.from(await response.arrayBuffer());
}

// The list of language pairs, kept on disk so translation also works offline.
async function loadRegistry() {
  if (!registry) {
    registry = (async () => {
      const file = path.join(folder(), 'registry.json');
      try {
        const data = JSON.parse((await download(`${REGISTRY}registry.json`)).toString('utf8'));
        fs.mkdirSync(folder(), { recursive: true });
        fs.writeFileSync(file, JSON.stringify(data));
        return data;
      } catch (error) {
        try { return JSON.parse(fs.readFileSync(file, 'utf8')); } catch { throw error; }
      }
    })();
    registry.catch(() => { registry = null; });
  }
  return registry;
}

async function sourceLanguages() {
  return Object.keys(await loadRegistry()).filter(pair => pair.endsWith('en')).map(pair => pair.slice(0, 2));
}

async function modelFile(pair, entry, onDownload) {
  const file = path.join(folder(), pair, entry.name);
  const check = buffer => crypto.createHash('sha256').update(buffer).digest('hex') === entry.expectedSha256Hash;
  try {
    const cached = fs.readFileSync(file);
    if (check(cached)) return cached;
  } catch {}
  onDownload();
  const buffer = await download(`${REGISTRY}${pair}/${entry.name}`);
  if (!check(buffer)) throw new Error(`model file ${entry.name} failed its checksum`);
  fs.mkdirSync(path.dirname(file), { recursive: true });
  fs.writeFileSync(file, buffer);
  return buffer;
}

const arrayBuffer = buffer => buffer.buffer.slice(buffer.byteOffset, buffer.byteOffset + buffer.byteLength);

// Model files for `from` -> English, from disk or downloaded once. `onDownload` fires if a download starts.
function loadModel(from, onDownload = () => {}) {
  const pair = `${from}en`;
  if (!models.has(pair)) {
    const promise = (async () => {
      const entry = (await loadRegistry())[pair];
      if (!entry) throw new Error(`no on-device model for this language (${from})`);
      let announced = false;
      const announce = () => { if (!announced) { announced = true; onDownload(); } };
      const [model, shortlist, vocab] = await Promise.all(['model', 'lex', 'vocab'].map(part => modelFile(pair, entry[part], announce)));
      return { model: arrayBuffer(model), shortlist: arrayBuffer(shortlist), vocabs: [arrayBuffer(vocab)] };
    })();
    promise.catch(() => models.delete(pair));
    models.set(pair, promise);
  }
  return models.get(pair);
}

function startWorker() {
  const worker = new Worker(BOOT, { eval: true, workerData: { file: WORKER_FILE } });
  const waiting = new Map();
  let nextId = 1;
  const fail = error => { for (const { reject } of waiting.values()) reject(error); waiting.clear(); };
  worker.on('message', ({ id, result, error }) => {
    const call = waiting.get(id);
    if (!call) return;
    waiting.delete(id);
    if (error) call.reject(Object.assign(new Error(error.message), { name: error.name })); else call.resolve(result);
  });
  worker.on('error', fail);
  worker.on('exit', () => fail(new Error('the translator stopped')));
  worker.unref();
  const call = (name, ...args) => new Promise((resolve, reject) => {
    const id = nextId++;
    waiting.set(id, { resolve, reject });
    worker.postMessage({ id, name, args });
  });
  return { call, ready: call('initialize', { cacheSize: 2 ** 14 }), loaded: new Map(), busy: 0, worker };
}

async function translateOn(slot, from, texts) {
  await slot.ready;
  if (!slot.loaded.has(from)) {
    // A first tiny translation warms the engine up, so the page's first batch isn't the slow one.
    slot.loaded.set(from, loadModel(from)
      .then(buffers => slot.call('loadTranslationModel', { from, to: 'en' }, buffers))
      .then(() => slot.call('translate', { models: [{ from, to: 'en' }], texts: [{ text: 'Hallo', html: false }] })));
    slot.loaded.get(from).catch(() => slot.loaded.delete(from));
  }
  await slot.loaded.get(from);
  if (!texts.length) return [];
  const responses = await slot.call('translate', { models: [{ from, to: 'en' }], texts: texts.map(text => ({ text, html: true })) });
  return responses.map(response => response.target.text);
}

function workers() {
  if (!pool) pool = Array.from({ length: options.workers }, startWorker);
  return pool;
}

// Gets the translator ready for a page in `from` when that language's model is already on disk,
// so pressing Translate starts at once. Never downloads anything by itself.
async function prepare(from) {
  try {
    const entry = (await loadRegistry())[`${from}en`];
    if (!entry || !['model', 'lex', 'vocab'].every(part => fs.existsSync(path.join(folder(), `${from}en`, entry[part].name)))) return;
    await Promise.all(workers().map(slot => translateOn(slot, from, [])));
  } catch {}
}

// Translates HTML snippets from `from` to English on the least busy worker.
async function translate(texts, from) {
  workers();
  const slot = pool.reduce((best, item) => (item.busy < best.busy ? item : best));
  slot.busy++;
  try { return await translateOn(slot, from, texts); } finally { slot.busy--; }
}

function shutdown() {
  if (pool) for (const slot of pool) slot.worker.terminate();
  pool = null;
}

module.exports = { configure, translate, prepare, loadModel, sourceLanguages, shutdown };
