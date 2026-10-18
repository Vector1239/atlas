// The toolbar's only bridge to Atlas: send browser commands and hear page state.
const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('atlasBrowser', {
  command: (action, value) => ipcRenderer.send('browser:command', String(action), value == null ? '' : String(value)),
  onState: listener => ipcRenderer.on('browser:state', (_event, state) => listener(state)),
  onFocusAddress: listener => ipcRenderer.on('browser:focus-address', () => listener())
});
