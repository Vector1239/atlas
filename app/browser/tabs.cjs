// Atlas's in-app browser: web links open as tabs in the main window, beside an "Atlas" tab.
// Every tab is a WebContentsView, not an iframe, so sites that refuse embedding still open.
// Web pages have no preload, no Node and their own persistent session; only the tab bar talks to Atlas.
const { WebContentsView, Menu, app, clipboard, ipcMain, session, shell } = require('electron');
const path = require('node:path');
const fs = require('node:fs');
const { isWeb, addressURL, chromeUserAgent } = require('./address.cjs');
const { PageTranslator, isEnglish } = require('./translate.cjs');
const { prepare: prepareTranslation } = require('./local-translator.cjs');

const STRIP = 40, TOOLBAR = 40;
const BUTTONS = { strip: { x: 16, y: 14 }, plain: { x: 19, y: 18 } };
let win = null, atlas = null, bar = null, tabs = [], active = null, nextId = 1, sessionReady = false, prefs = null;

// Remembered browser choices, kept beside Atlas's other app data.
function preferences() {
  if (!prefs) {
    try { prefs = JSON.parse(fs.readFileSync(path.join(app.getPath('userData'), 'browser.json'), 'utf8')); } catch { prefs = {}; }
  }
  return prefs;
}
function remember(changes) {
  Object.assign(preferences(), changes);
  try { fs.writeFileSync(path.join(app.getPath('userData'), 'browser.json'), JSON.stringify(prefs) + '\n'); } catch {}
  send();
}

function browserSession() {
  const ses = session.fromPartition('persist:atlas-browser');
  if (!sessionReady) {
    sessionReady = true;
    ses.setUserAgent(chromeUserAgent(app.userAgentFallback));
    const allowed = new Set(['fullscreen', 'clipboard-sanitized-write']);
    ses.setPermissionRequestHandler((_wc, permission, callback) => callback(allowed.has(permission)));
    ses.setPermissionCheckHandler((_wc, permission) => allowed.has(permission));
  }
  return ses;
}

function outside(url) {
  try { if (isWeb(url) || new URL(url).protocol === 'mailto:') shell.openExternal(url); } catch {}
}

const current = () => tabs.find(tab => tab.id === active) || null;
const alive = view => view && !view.webContents.isDestroyed();

function layout() {
  if (!win || win.isDestroyed()) return;
  const [width, height] = win.getContentSize();
  const tab = current();
  const top = tabs.length ? STRIP + (tab ? TOOLBAR : 0) : 0;
  bar.setVisible(tabs.length > 0);
  bar.setBounds({ x: 0, y: 0, width, height: top });
  for (const view of [atlas, ...tabs.map(item => item.view)]) {
    const shown = view === (tab ? tab.view : atlas);
    view.setVisible(shown);
    if (shown) view.setBounds({ x: 0, y: top, width, height: Math.max(0, height - top) });
  }
  if (process.platform === 'darwin' && win.setWindowButtonPosition) win.setWindowButtonPosition(tabs.length ? BUTTONS.strip : BUTTONS.plain);
}

function send() {
  if (!alive(bar)) return;
  const tab = current();
  const page = tab && alive(tab.view) ? tab.view.webContents : null;
  bar.webContents.send('browser:state', {
    active,
    tabs: tabs.map(item => ({ id: item.id, title: alive(item.view) ? item.view.webContents.getTitle() : '', loading: alive(item.view) && item.view.webContents.isLoading() })),
    page: page && {
      url: page.getURL(), title: page.getTitle(), loading: page.isLoading(),
      back: page.navigationHistory.canGoBack(), forward: page.navigationHistory.canGoForward(),
      language: tab.language, failure: tab.failure, translation: tab.translator.state()
    }
  });
}

function select(id) {
  active = tabs.some(tab => tab.id === id) ? id : null;
  layout(); send();
  const tab = current();
  (tab ? tab.view : atlas).webContents.focus();
}

function close(id) {
  const index = tabs.findIndex(tab => tab.id === id);
  if (index < 0) return;
  const [tab] = tabs.splice(index, 1);
  tab.translator.dispose();
  win.contentView.removeChildView(tab.view);
  if (alive(tab.view)) tab.view.webContents.close();
  if (active === id) active = (tabs[index] || tabs[index - 1] || {}).id ?? null;
  select(active);
}

function contextMenu(tab, params) {
  const wc = tab.view.webContents, items = [];
  if (params.linkURL && isWeb(params.linkURL)) {
    items.push({ label: 'Open Link in New Tab', click: () => openTab(params.linkURL, { after: tab.id, background: true, translate: tab.translator.on }) },
      { label: 'Open Link in Default Browser', click: () => outside(params.linkURL) },
      { label: 'Copy Link', click: () => clipboard.writeText(params.linkURL) }, { type: 'separator' });
  }
  if (params.isEditable) items.push({ role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { type: 'separator' });
  else if (params.selectionText) items.push({ role: 'copy' }, { type: 'separator' });
  items.push({ label: 'Back', enabled: wc.navigationHistory.canGoBack(), click: () => command('back') },
    { label: 'Forward', enabled: wc.navigationHistory.canGoForward(), click: () => command('forward') },
    { label: 'Reload', click: () => command('reload') }, { type: 'separator' },
    { label: tab.translator.on ? 'Show Original' : 'Translate to English', click: () => command('translate') },
    { label: 'Always Translate Foreign Pages', type: 'checkbox', checked: Boolean(preferences().autoTranslate), click: () => command('auto-translate') },
    { label: 'Open Page in Default Browser', click: () => command('external') });
  Menu.buildFromTemplate(items).popup({ window: win });
}

// Reads the page's declared language; with "Always translate" on, foreign pages translate by themselves.
function readLanguage(tab) {
  if (!alive(tab.view)) return;
  tab.view.webContents.executeJavaScript('document.documentElement.lang || ""', false).then(language => {
    tab.language = String(language).slice(0, 12);
    if (preferences().autoTranslate && tab.language && !isEnglish(tab.language) && !tab.translator.on) tab.translator.start();
    else if (tab.language && !isEnglish(tab.language)) prepareTranslation(tab.language.split('-')[0].toLowerCase());
    send();
  }).catch(() => {});
}

// Opens a web link in a new tab and shows it unless `background` is set.
function openTab(url, { after = null, background = false, translate = false } = {}) {
  if (!win || win.isDestroyed()) return;
  if (!isWeb(url)) return outside(url);
  const view = new WebContentsView({ webPreferences: { session: browserSession(),
    nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true } });
  const tab = { id: nextId++, view, failure: '', language: '' };
  tab.translator = new PageTranslator(view.webContents, send, () => tab.language);
  const index = tabs.findIndex(item => item.id === after);
  tabs.splice(index < 0 ? tabs.length : index + 1, 0, tab);
  win.contentView.addChildView(view);
  win.contentView.addChildView(bar);
  const wc = view.webContents;
  wc.setWindowOpenHandler(({ url: next }) => {
    if (isWeb(next)) openTab(next, { after: tab.id, translate: tab.translator.on }); else outside(next);
    return { action: 'deny' };
  });
  wc.on('will-navigate', (event, next) => { if (!isWeb(next)) { event.preventDefault(); outside(next); } });
  wc.on('did-start-loading', () => { tab.failure = ''; if (!tab.translator.on) tab.translator.failure = ''; });
  wc.on('did-navigate', () => { tab.language = ''; tab.translator.navigated(); });
  for (const name of ['did-start-loading', 'did-stop-loading', 'did-navigate', 'did-navigate-in-page', 'page-title-updated']) wc.on(name, send);
  wc.on('did-finish-load', () => readLanguage(tab));
  wc.on('did-fail-load', (_event, code, text, _url, mainFrame) => {
    if (mainFrame && code !== -3) { tab.failure = `Couldn’t load this page (${text.replace(/^ERR_/, '').replaceAll('_', ' ').toLowerCase()})`; send(); }
  });
  wc.on('context-menu', (_event, params) => contextMenu(tab, params));
  wc.loadURL(url);
  if (translate) tab.translator.start();
  if (background) { layout(); send(); } else select(tab.id);
  if (win.isMinimized()) win.restore();
  win.show();
}

// Handles toolbar buttons and the app menu; actions without a web tab open fall through to Atlas.
function command(action, value = '') {
  if (!win || win.isDestroyed()) return;
  const tab = current();
  if (action === 'select') return select(value === 'atlas' ? null : Number(value));
  if (action === 'close') return close(Number(value));
  if (action === 'close-current') return tab ? close(tab.id) : win.close();
  if (action === 'next' || action === 'previous') {
    const order = [null, ...tabs.map(item => item.id)];
    const step = action === 'next' ? 1 : order.length - 1;
    return select(order[(order.indexOf(active) + step) % order.length]);
  }
  if (!tab) {
    if (action === 'reload') atlas.webContents.reload();
    return;
  }
  const wc = tab.view.webContents, history = wc.navigationHistory;
  if (action === 'back' && history.canGoBack()) history.goBack();
  else if (action === 'forward' && history.canGoForward()) history.goForward();
  else if (action === 'reload') wc.reload();
  else if (action === 'stop') wc.stop();
  else if (action === 'external') outside(wc.getURL());
  else if (action === 'translate') { if (tab.translator.on) tab.translator.stop(); else tab.translator.start(); }
  else if (action === 'auto-translate') remember({ autoTranslate: !preferences().autoTranslate });
  else if (action === 'translate-options') {
    Menu.buildFromTemplate([
      { label: tab.translator.on ? 'Show Original' : 'Translate to English', click: () => command('translate') },
      { label: 'Always Translate Foreign Pages', type: 'checkbox', checked: Boolean(preferences().autoTranslate), click: () => command('auto-translate') }
    ]).popup({ window: win });
  }
  else if (action === 'focus-address') { bar.webContents.focus(); bar.webContents.send('browser:focus-address'); }
  else if (action === 'go') { const url = addressURL(value); if (url) { wc.loadURL(url); wc.focus(); } else send(); }
}

// The web contents the View menu (zoom, developer tools) should act on.
function focusedContents() {
  if (!win || win.isDestroyed()) return null;
  const tab = current();
  return (tab ? tab.view : atlas).webContents;
}

function attach(window, atlasView) {
  win = window; atlas = atlasView; tabs = []; active = null;
  bar = new WebContentsView({ webPreferences: { preload: path.join(__dirname, 'toolbar-preload.cjs'),
    nodeIntegration: false, contextIsolation: true, sandbox: true } });
  bar.setBackgroundColor('#f7f6f3');
  bar.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  bar.webContents.on('will-navigate', event => event.preventDefault());
  bar.webContents.on('did-finish-load', send);
  bar.webContents.loadFile(path.join(__dirname, 'toolbar.html'));
  win.contentView.addChildView(atlas);
  win.contentView.addChildView(bar);
  layout();
  win.on('resize', layout);
  win.on('closed', () => {
    for (const view of [bar, ...tabs.map(tab => tab.view)]) if (alive(view)) view.webContents.close();
    win = atlas = bar = null; tabs = []; active = null;
  });
}

ipcMain.on('browser:command', (event, action, value) => {
  if (alive(bar) && event.sender === bar.webContents && typeof action === 'string') command(action, typeof value === 'string' ? value : '');
});

module.exports = { attach, openTab, command, focusedContents };
