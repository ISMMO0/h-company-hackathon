const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('overlay', {
  onMessage: (cb) => ipcRenderer.on('brain', (_event, msg) => cb(msg)),
  hidden: () => ipcRenderer.send('hidden'),
  send: (msg) => ipcRenderer.send('panel', msg),
  interactive: (on) => ipcRenderer.send('interactive', on),
});
