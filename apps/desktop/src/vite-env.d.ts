/// <reference types="vite/client" />

type IpcRequest = {
  path: string;
  method?: 'GET' | 'POST';
  token?: string;
  body?: unknown;
  upload?: { name: string; type: string; bytes: Uint8Array };
};

interface Window {
  smartOrder?: {
    platform: string;
    version: string;
    requestApi: <T>(request: IpcRequest) => Promise<T>;
    requestPrint: <T>(request: IpcRequest) => Promise<T>;
  };
}

interface Window {
  smartOrder?: { platform: string; version: string };
}

