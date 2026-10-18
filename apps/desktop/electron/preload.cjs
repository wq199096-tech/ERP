const { contextBridge, ipcRenderer } = require('electron');
contextBridge.exposeInMainWorld('smartOrder', {
  platform: process.platform,
  version: '0.1.0',
  requestApi: (request) => ipcRenderer.invoke('smartorder:api', request),
  requestPrint: (request) => ipcRenderer.invoke('smartorder:print', request),
});

