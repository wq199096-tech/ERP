const { contextBridge } = require('electron');
contextBridge.exposeInMainWorld('smartOrder', {
  platform: process.platform,
  version: '0.1.0',
});

