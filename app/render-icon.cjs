const { app, BrowserWindow } = require('electron');
const fs = require('node:fs');
const path = require('node:path');
app.whenReady().then(async () => {
  const window = new BrowserWindow({ width: 1024, height: 1024, show: false, frame: false, transparent: true, webPreferences: { offscreen: true, nodeIntegration: false, contextIsolation: true, sandbox: true } });
  const svg = fs.readFileSync(path.join(__dirname, 'assets/Atlas.svg'), 'utf8');
  await window.loadURL(`data:text/html;charset=utf-8,${encodeURIComponent('<html style="background:transparent"><body style="margin:0">' + svg + '</body></html>')}`);
  await new Promise(resolve => setTimeout(resolve, 500));
  fs.writeFileSync(path.join(__dirname, 'assets/Atlas.png'), (await window.webContents.capturePage()).toPNG());
  app.quit();
});
