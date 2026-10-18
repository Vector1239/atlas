const { app, BrowserWindow, WebContentsView, Menu, dialog, session } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const tabs = require('./browser/tabs.cjs');

app.setName('Atlas');
app.userAgentFallback += ` Atlas/${app.getVersion()} (+https://github.com/Vector1239/atlas)`;
let backend, window, atlas, baseURL, exiting = false;
const project = process.env.ATLAS_PROJECT || path.join(os.homedir(), 'Projects/Atlas/germany-life-hermes');
const python = process.env.ATLAS_PYTHON || '/opt/homebrew/bin/python3.12';
const bundle = app.isPackaged ? path.resolve(__dirname, '../../..') : '';

// A second launch only focuses the first window; it must not start its own backend.
const primary = app.requestSingleInstanceLock();
if (!primary) app.quit();
app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } });

// Web links from Atlas open as tabs in the same window; see browser/tabs.cjs.
function external(url) {
  try { if (['https:', 'http:'].includes(new URL(url).protocol)) tabs.openTab(url); } catch {}
}
function createWindow(url) {
  baseURL = new URL(url).origin;
  window = new BrowserWindow({ title: 'Atlas', width: 1320, height: 900, minWidth: 720, minHeight: 600,
    backgroundColor: '#fbfbfa', titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 19, y: 18 },
    icon: path.join(__dirname, 'assets/Atlas.png'), show: false });
  // Atlas itself is the first tab: a view beside the web tabs, not the window's own page.
  atlas = new WebContentsView({ webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true } });
  atlas.setBackgroundColor('#fbfbfa');
  tabs.attach(window, atlas);
  atlas.webContents.setWindowOpenHandler(({ url }) => { external(url); return { action: 'deny' }; });
  atlas.webContents.on('will-navigate', (event, next) => {
    if (new URL(next).origin !== baseURL) { event.preventDefault(); external(next); }
  });
  atlas.webContents.once('did-finish-load', () => { window.show(); atlas.webContents.focus(); });
  const launchURL = new URL(url);
  if (process.env.ATLAS_OPEN_UPDATES === '1') launchURL.searchParams.set('settings', 'updates');
  atlas.webContents.loadURL(launchURL.href);
  window.on('closed', () => { window = atlas = null; });
}

function zoom(step) {
  const contents = tabs.focusedContents();
  if (contents) contents.setZoomLevel(step === 0 ? 0 : contents.getZoomLevel() + step);
}

app.whenReady().then(() => {
  if (!primary) return;
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Atlas', submenu: [{ role: 'about', label: 'About Atlas' }, { label: 'Check for Updates…', click: () => { if (window && baseURL) { tabs.command('select', 'atlas'); atlas.webContents.loadURL(new URL('/?settings=updates&checkUpdates=1', baseURL).href); window.show(); window.focus(); } } }, { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] },
    { role: 'editMenu' },
    // View and Window act on the visible tab, since Atlas and each web page are separate views.
    { label: 'View', submenu: [
      { label: 'Reload', accelerator: 'CmdOrCtrl+R', click: () => tabs.command('reload') },
      { label: 'Back', accelerator: 'CmdOrCtrl+[', click: () => tabs.command('back') },
      { label: 'Forward', accelerator: 'CmdOrCtrl+]', click: () => tabs.command('forward') },
      { label: 'Open Location…', accelerator: 'CmdOrCtrl+L', click: () => tabs.command('focus-address') },
      { label: 'Translate Page', click: () => tabs.command('translate') },
      { type: 'separator' },
      { label: 'Actual Size', accelerator: 'CmdOrCtrl+0', click: () => zoom(0) },
      { label: 'Zoom In', accelerator: 'CmdOrCtrl+Plus', click: () => zoom(0.5) },
      { label: 'Zoom Out', accelerator: 'CmdOrCtrl+-', click: () => zoom(-0.5) },
      { type: 'separator' },
      { label: 'Toggle Developer Tools', accelerator: 'Alt+CmdOrCtrl+I', click: () => tabs.focusedContents()?.toggleDevTools() },
      { role: 'togglefullscreen' }
    ] },
    { label: 'Window', submenu: [
      { role: 'minimize' }, { role: 'zoom' }, { type: 'separator' },
      { label: 'Show Next Tab', accelerator: 'Ctrl+Tab', click: () => tabs.command('next') },
      { label: 'Show Previous Tab', accelerator: 'Ctrl+Shift+Tab', click: () => tabs.command('previous') },
      { label: 'Close Tab', accelerator: 'CmdOrCtrl+W', click: () => tabs.command('close-current') },
      { type: 'separator' }, { role: 'front' }
    ] }
  ]));
  session.defaultSession.setPermissionRequestHandler((_wc, _permission, callback) => callback(false));
  session.defaultSession.setPermissionCheckHandler(() => false);
  if (!fs.existsSync(project) || !fs.existsSync(python)) {
    dialog.showErrorBox('Atlas needs its local files', `The Atlas project or Python runtime could not be found.\nProject: ${project}\nPython: ${python}`);
    app.quit(); return;
  }
  const logs = path.join(project, 'state'); fs.mkdirSync(logs, { recursive: true });
  const log = fs.openSync(path.join(logs, 'atlas-app.log'), 'a');
  backend = spawn(python, ['-u', path.join(__dirname, 'backend.py')], {
    cwd: project, env: { ...process.env, ATLAS_PROJECT: project, ATLAS_APP_BUNDLE: bundle, ATLAS_DESKTOP_PID: String(process.pid), PYTHONUNBUFFERED: '1', PATH: `/opt/homebrew/bin:${os.homedir()}/.local/bin:/usr/bin:/bin:/usr/sbin:/sbin` },
    stdio: ['ignore', 'pipe', log]
  });
  fs.closeSync(log);
  let buffer = '', started = false;
  const timer = setTimeout(() => { if (!started) { dialog.showErrorBox('Atlas could not open', 'The local app service did not start. Details are in the project’s state/atlas-app.log file.'); app.quit(); } }, 30000);
  backend.stdout.on('data', chunk => {
    buffer += chunk;
    let lineEnd;
    while ((lineEnd = buffer.indexOf('\n')) >= 0) {
      const line = buffer.slice(0, lineEnd); buffer = buffer.slice(lineEnd + 1);
      try { const data = JSON.parse(line); if (data.url && !started) { started = true; clearTimeout(timer); createWindow(data.url); } } catch {}
    }
  });
  backend.on('error', error => { clearTimeout(timer); dialog.showErrorBox('Atlas could not start', error.message); app.quit(); });
  backend.on('exit', code => { if (!exiting && code !== 0) { dialog.showErrorBox('Atlas stopped unexpectedly', 'Please reopen Atlas. Your data is saved locally.'); app.quit(); } });
});

app.on('window-all-closed', () => app.quit());
process.on('SIGTERM', () => app.quit());
app.on('before-quit', () => { exiting = true; if (backend && backend.exitCode === null) backend.kill('SIGTERM'); });
