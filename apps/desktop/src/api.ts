import type { OrderPage, PrintJob } from './types';

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api/v1';

async function browserRequest<T>(path: string, request: IpcRequest): Promise<T> {
  const response = await fetch(`${API_URL}${path}`, {
    method: request.method ?? 'GET',
    body: request.upload
      ? (() => {
          const data = new FormData();
          data.append('file', new Blob([request.upload.bytes as BlobPart], { type: request.upload.type }), request.upload.name);
          return data;
        })()
      : request.body === undefined ? undefined : JSON.stringify(request.body),
    headers: {
      ...(request.upload || request.body === undefined ? {} : { 'Content-Type': 'application/json' }),
      ...(request.token ? { Authorization: `Bearer ${request.token}` } : {}),
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? '请求失败');
  }
  return response.json() as Promise<T>;
}

const apiRequest = <T>(path: string, request: Omit<IpcRequest, 'path'> = {}) =>
  window.smartOrder?.requestApi<T>({ path, ...request }) ?? browserRequest<T>(path, { path, ...request });

const agentRequest = <T>(path: string, request: Omit<IpcRequest, 'path'> = {}) => {
  if (!window.smartOrder) return Promise.reject(new Error('本机打印仅可在 Windows 客户端中使用'));
  return window.smartOrder.requestPrint<T>({ path, ...request });
};

export type PreparedTask = {
  id: string;
  idempotency_key: string;
  status: string;
  payload: Record<string, unknown>;
};

export const api = {
  login: (email: string, password: string) =>
    apiRequest<{
      access_token: string;
      user: { name: string; role?: string };
      tenant: { name: string };
    }>('/auth/login', { method: 'POST', body: { email, password } }),
  shops: (token: string) =>
    apiRequest<Array<{ id: string; name: string; platform: string; status: string }>>('/shops', { token }),
  orders: (token: string, query: URLSearchParams) =>
    apiRequest<OrderPage>(`/orders?${query}`, { token }),
  dashboard: (token: string) => apiRequest<{
    generated_at: string;
    orders_total: number;
    pending_shipment: number;
    exception_orders: number;
    print_jobs: Record<string, number>;
    has_data: boolean;
  }>('/dashboard/summary', { token }),
  syncMock: (token: string) =>
    apiRequest<{ received: number; created: number; updated: number }>(
      '/orders/mock/sync?count=1000', { method: 'POST', token },
    ),
  audit: (token: string, orderIds: string[]) =>
    apiRequest<{ updated: number; blocked: Record<string, string[]> }>('/orders/batch/audit', {
      method: 'POST', token, body: { order_ids: orderIds },
    }),
  preparePrint: (token: string, orderIds: string[], printerName: string, jobTypes: string[]) =>
    apiRequest<{ tasks: PreparedTask[]; blocked: Record<string, string[]> }>('/orders/print/prepare', {
      method: 'POST', token,
      body: { order_ids: orderIds, printer_name: printerName, job_types: jobTypes, operation: 'NORMAL' },
    }),
  receipt: (token: string, serverTaskId: string, job: PrintJob) =>
    apiRequest(`/orders/print/tasks/${serverTaskId}/receipt`, {
      method: 'POST', token,
      body: {
        agent_job_id: job.id,
        status: job.status,
        waybill_no: job.waybill_no,
        system_job_id: job.system_job_id,
        output_file: job.output_file,
        error_message: job.error_message,
      },
    }),
  importOrders: async (token: string, file: File) =>
    apiRequest<{ rows: number; created: number; errors: unknown[] }>('/orders/import', {
      method: 'POST', token,
      upload: { name: file.name, type: file.type, bytes: new Uint8Array(await file.arrayBuffer()) },
    }),
};

export const printAgent = {
  health: () => agentRequest<{ status: string }>('/health'),
  printers: () => agentRequest<Array<{ name: string; is_default: boolean; is_online: boolean }>>('/printers'),
  jobs: () => agentRequest<PrintJob[]>('/jobs'),
  create: (body: object) => agentRequest<PrintJob>('/jobs', { method: 'POST', body }),
  retry: (id: string) => agentRequest<PrintJob>(`/jobs/${id}/retry`, { method: 'POST' }),
  preview: async (jobType: string, payload: object) => {
    const result = await agentRequest<{ binary: string; type: string }>(`/preview/${jobType}`, {
      method: 'POST', body: payload,
    });
    const bytes = Uint8Array.from(atob(result.binary), (character) => character.charCodeAt(0));
    return new Blob([bytes], { type: result.type });
  },
};
