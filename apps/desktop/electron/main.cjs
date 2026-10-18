const { app, BrowserWindow, ipcMain, shell } = require('electron');
const path = require('node:path');

const API_URL = process.env.SMARTORDER_API_URL || 'http://127.0.0.1:8000/api/v1';
const AGENT_URL = process.env.SMARTORDER_PRINT_AGENT_URL || 'http://127.0.0.1:17321/api/v1';
const AGENT_TOKEN = process.env.PRINT_AGENT_TOKEN || 'replace-with-local-agent-token';

const apiPaths = [
  /^\/auth\/login$/,
  /^\/shops$/,
  /^\/dashboard\/summary$/,
  /^\/orders(?:$|\?|\/)/,
];
const agentPaths = [
  /^\/health$/,
  /^\/printers$/,
  /^\/jobs(?:$|\?|\/)/,
  /^\/preview\/(WAYBILL|MANIFEST_A4|MANIFEST_A5|MANIFEST_80|PRODUCT_LABEL)$/,
  /^\/queue\/(pause|resume)$/,
];

function allowed(pathname, patterns) {
  return typeof pathname === 'string' && patterns.some((pattern) => pattern.test(pathname));
}

async function proxyRequest(baseUrl, request, patterns, serviceToken) {
  if (!allowed(request.path, patterns)) throw new Error('请求路径不在 Electron IPC 白名单中');
  const method = request.method || 'GET';
  if (!['GET', 'POST'].includes(method)) throw new Error('请求方法不受支持');
  const headers = { ...(request.token ? { Authorization: `Bearer ${request.token}` } : {}) };
  if (serviceToken) headers.Authorization = `Bearer ${serviceToken}`;
  let body;
  if (request.upload) {
    const form = new FormData();
    form.append('file', new Blob([request.upload.bytes], { type: request.upload.type }), request.upload.name);
    body = form;
  } else if (request.body !== undefined) {
    headers['Content-Type'] = 'application/json';
    body = JSON.stringify(request.body);
  }
  const response = await fetch(`${baseUrl}${request.path}`, { method, headers, body });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(typeof detail.detail === 'string' ? detail.detail : JSON.stringify(detail.detail));
  }
  if (response.headers.get('content-type')?.includes('application/pdf')) {
    return { binary: Buffer.from(await response.arrayBuffer()).toString('base64'), type: 'application/pdf' };
  }
  return response.json();
}

ipcMain.handle('smartorder:api', (_event, request) =>
  proxyRequest(API_URL, request, apiPaths));
ipcMain.handle('smartorder:print', (_event, request) =>
  proxyRequest(AGENT_URL, request, agentPaths, AGENT_TOKEN));

function createWindow() {
  const window = new BrowserWindow({
    width: 1440,
    height: 900,
    minWidth: 1180,
    minHeight: 720,
    title: '智单 ERP',
    backgroundColor: '#f4f7fb',
    autoHideMenuBar: true,
    webPreferences: {
      preload: path.join(__dirname, 'preload.cjs'),
      contextIsolation: true,
      nodeIntegration: false,
      sandbox: true,
    },
  });
  window.webContents.setWindowOpenHandler(({ url }) => {
    if (url.startsWith('blob:')) return { action: 'allow' };
    if (url.startsWith('https://')) shell.openExternal(url);
    return { action: 'deny' };
  });
  if (app.isPackaged) window.loadFile(path.join(__dirname, '..', 'dist', 'index.html'));
  else window.loadURL(process.env.SMARTORDER_RENDERER_URL || 'http://127.0.0.1:5173');
}

app.whenReady().then(() => {
  createWindow();
  app.on('activate', () => BrowserWindow.getAllWindows().length === 0 && createWindow());
});
app.on('window-all-closed', () => process.platform !== 'darwin' && app.quit());
