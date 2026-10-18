// Atlas's in-app browser: one window with a small toolbar view above the page view.
// Pages load in WebContentsView, not an iframe, so sites that refuse embedding still open.
// The page has no preload, no Node and its own persistent session; only the toolbar talks to Atlas.
const { BrowserWindow, WebContentsView, Menu, app, clipboard, ipcMain, session, shell } = require('electron');
const path = require('node:path');
const { isWeb, addressURL, chromeUserAgent } = require('./address.cjs');

const BAR = 44;
let win = null, bar = null, page = null, pending = null, failure = '', sessionReady = false;

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

function send() {
  if (!bar || !page || bar.webContents.isDestroyed() || page.webContents.isDestroyed()) return;
  const wc = page.webContents, history = wc.navigationHistory;
  bar.webContents.send('browser:state', {
    url: wc.getURL(), title: wc.getTitle(), loading: wc.isLoading(),
    back: history.canGoBack(), forward: history.canGoForward(), failure
  });
  win.setTitle(wc.getTitle() || 'Atlas Browser');
}

function layout() {
  const [width, height] = win.getContentSize();
  bar.setBounds({ x: 0, y: 0, width, height: BAR });
  page.setBounds({ x: 0, y: BAR, width, height: Math.max(0, height - BAR) });
}

function command(action, value) {
  if (!page) return;
  const wc = page.webContents, history = wc.navigationHistory;
  if (action === 'back' && history.canGoBack()) history.goBack();
  else if (action === 'forward' && history.canGoForward()) history.goForward();
  else if (action === 'reload') wc.reload();
  else if (action === 'stop') wc.stop();
  else if (action === 'external') outside(wc.getURL());
  else if (action === 'focus-address') { bar.webContents.focus(); bar.webContents.send('browser:focus-address'); }
  else if (action === 'go') { const url = addressURL(value); if (url) { wc.loadURL(url); wc.focus(); } else send(); }
}

// Browser shortcuts, handled before the app menu so Reload reloads the page rather than Atlas.
function shortcuts(contents) {
  contents.on('before-input-event', (event, input) => {
    if (input.type !== 'keyDown' || !(input.meta || input.control) || input.alt) return;
    const key = input.key.toLowerCase();
    const action = { '[': 'back', ']': 'forward', arrowleft: 'back', arrowright: 'forward', r: 'reload', l: 'focus-address' }[key];
    if (!action || (key.startsWith('arrow') && contents === bar.webContents)) return;
    event.preventDefault();
    command(action);
  });
}

function contextMenu(params) {
  const wc = page.webContents, items = [];
  if (params.linkURL && isWeb(params.linkURL)) {
    items.push({ label: 'Open Link in Default Browser', click: () => outside(params.linkURL) },
      { label: 'Copy Link', click: () => clipboard.writeText(params.linkURL) }, { type: 'separator' });
  }
  if (params.isEditable) items.push({ role: 'cut' }, { role: 'copy' }, { role: 'paste' }, { type: 'separator' });
  else if (params.selectionText) items.push({ role: 'copy' }, { type: 'separator' });
  items.push({ label: 'Back', enabled: wc.navigationHistory.canGoBack(), click: () => command('back') },
    { label: 'Forward', enabled: wc.navigationHistory.canGoForward(), click: () => command('forward') },
    { label: 'Reload', click: () => command('reload') }, { type: 'separator' },
    { label: 'Open Page in Default Browser', click: () => command('external') });
  Menu.buildFromTemplate(items).popup({ window: win });
}

function create(icon) {
  win = new BrowserWindow({ title: 'Atlas Browser', width: 1180, height: 860, minWidth: 520, minHeight: 400,
    backgroundColor: '#fbfbfa', titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 16, y: 15 }, icon, show: false });
  bar = new WebContentsView({ webPreferences: { preload: path.join(__dirname, 'toolbar-preload.cjs'),
    nodeIntegration: false, contextIsolation: true, sandbox: true } });
  page = new WebContentsView({ webPreferences: { session: browserSession(),
    nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true } });
  win.contentView.addChildView(page);
  win.contentView.addChildView(bar);
  layout();
  win.on('resize', layout);

  const wc = page.webContents;
  wc.setWindowOpenHandler(({ url }) => { if (isWeb(url)) wc.loadURL(url); else outside(url); return { action: 'deny' }; });
  wc.on('will-navigate', (event, url) => { if (!isWeb(url)) { event.preventDefault(); outside(url); } });
  wc.on('did-start-loading', () => { failure = ''; });
  for (const name of ['did-start-loading', 'did-stop-loading', 'did-navigate', 'did-navigate-in-page', 'page-title-updated']) wc.on(name, send);
  wc.on('did-fail-load', (_event, code, text, _url, mainFrame) => {
    if (mainFrame && code !== -3) { failure = `Couldn’t load this page (${text.replace(/^ERR_/, '').replaceAll('_', ' ').toLowerCase()})`; send(); }
  });
  wc.on('context-menu', (_event, params) => contextMenu(params));
  shortcuts(wc);
  shortcuts(bar.webContents);
  bar.webContents.setWindowOpenHandler(() => ({ action: 'deny' }));
  bar.webContents.on('will-navigate', event => event.preventDefault());
  bar.webContents.once('did-finish-load', () => {
    win.show();
    if (pending) { wc.loadURL(pending); pending = null; }
  });
  bar.webContents.loadFile(path.join(__dirname, 'toolbar.html'));
  win.on('closed', () => {
    for (const view of [bar, page]) if (!view.webContents.isDestroyed()) view.webContents.close();
    win = bar = page = pending = null;
  });
}

ipcMain.on('browser:command', (event, action, value) => {
  if (bar && event.sender === bar.webContents && typeof action === 'string') command(action, typeof value === 'string' ? value : '');
});

// Opens a web link in the Atlas browser window, creating it on first use.
function openInBrowser(url, icon) {
  if (!isWeb(url)) return outside(url);
  if (!win) { pending = url; create(icon); return; }
  if (pending) pending = url; else page.webContents.loadURL(url);
  if (win.isMinimized()) win.restore();
  win.show(); win.focus();
}

function closeBrowser() { if (win) win.close(); }

module.exports = { openInBrowser, closeBrowser };
