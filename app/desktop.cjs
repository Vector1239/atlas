const { app, BrowserWindow, Menu, dialog, session } = require('electron');
const { spawn } = require('node:child_process');
const path = require('node:path');
const fs = require('node:fs');
const os = require('node:os');
const { openInBrowser, closeBrowser } = require('./browser/window.cjs');

app.setName('Atlas');
app.userAgentFallback += ` Atlas/${app.getVersion()} (+https://github.com/Vector1239/atlas)`;
let backend, window, baseURL, exiting = false;
const project = process.env.ATLAS_PROJECT || path.join(os.homedir(), 'Projects/Atlas/germany-life-hermes');
const python = process.env.ATLAS_PYTHON || '/opt/homebrew/bin/python3.12';
const bundle = app.isPackaged ? path.resolve(__dirname, '../../..') : '';

// A second launch only focuses the first window; it must not start its own backend.
const primary = app.requestSingleInstanceLock();
if (!primary) app.quit();
app.on('second-instance', () => { if (window) { if (window.isMinimized()) window.restore(); window.show(); window.focus(); } });

// Web links from Atlas open in its own browser window; see browser/window.cjs.
function external(url) {
  try { if (['https:', 'http:'].includes(new URL(url).protocol)) openInBrowser(url, path.join(__dirname, 'assets/Atlas.png')); } catch {}
}
function createWindow(url) {
  baseURL = new URL(url).origin;
  window = new BrowserWindow({ title: 'Atlas', width: 1320, height: 900, minWidth: 720, minHeight: 600,
    backgroundColor: '#fbfbfa', titleBarStyle: 'hiddenInset', trafficLightPosition: { x: 19, y: 18 },
    icon: path.join(__dirname, 'assets/Atlas.png'), show: false,
    webPreferences: { nodeIntegration: false, contextIsolation: true, sandbox: true, webSecurity: true } });
  window.webContents.setWindowOpenHandler(({ url }) => { external(url); return { action: 'deny' }; });
  window.webContents.on('will-navigate', (event, next) => {
    if (new URL(next).origin !== baseURL) { event.preventDefault(); external(next); }
  });
  window.once('ready-to-show', () => window.show());
  const launchURL = new URL(url);
  if (process.env.ATLAS_OPEN_UPDATES === '1') launchURL.searchParams.set('settings', 'updates');
  window.loadURL(launchURL.href);
  window.on('closed', () => { window = null; closeBrowser(); });
}

app.whenReady().then(() => {
  if (!primary) return;
  Menu.setApplicationMenu(Menu.buildFromTemplate([
    { label: 'Atlas', submenu: [{ role: 'about', label: 'About Atlas' }, { label: 'Check for Updates…', click: () => { if (window && baseURL) { window.loadURL(new URL('/?settings=updates&checkUpdates=1', baseURL).href); window.show(); window.focus(); } } }, { type: 'separator' }, { role: 'hide' }, { role: 'hideOthers' }, { role: 'unhide' }, { type: 'separator' }, { role: 'quit' }] },
    { role: 'editMenu' }, { role: 'viewMenu' }, { role: 'windowMenu' }
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
