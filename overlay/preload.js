const { contextBridge, ipcRenderer } = require('electron');

contextBridge.exposeInMainWorld('overlay', {
  onMessage: (cb) => ipcRenderer.on('brain', (_event, msg) => cb(msg)),
  hidden: () => ipcRenderer.send('hidden'),
});
