import type { OrderPage, PrintJob } from './types';

export const API_URL = import.meta.env.VITE_API_URL ?? 'http://127.0.0.1:8000/api/v1';
export const AGENT_URL = import.meta.env.VITE_PRINT_AGENT_URL ?? 'http://127.0.0.1:17321/api/v1';
const AGENT_TOKEN = import.meta.env.VITE_PRINT_AGENT_TOKEN ?? 'replace-with-local-agent-token';

async function request<T>(url: string, options: RequestInit = {}, token?: string): Promise<T> {
  const response = await fetch(url, {
    ...options,
    headers: {
      ...(options.body instanceof FormData ? {} : { 'Content-Type': 'application/json' }),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
      ...options.headers,
    },
  });
  if (!response.ok) {
    const detail = await response.json().catch(() => ({ detail: response.statusText }));
    throw new Error(detail.detail ?? '请求失败');
  }
  return response.json() as Promise<T>;
}

export const api = {
  login: (email: string, password: string) =>
    request<{
      access_token: string;
      user: { name: string };
      tenant: { name: string };
    }>(`${API_URL}/auth/login`, { method: 'POST', body: JSON.stringify({ email, password }) }),
  shops: (token: string) =>
    request<Array<{ id: string; name: string; platform: string; status: string }>>(
      `${API_URL}/shops`, {}, token,
    ),
  orders: (token: string, query: URLSearchParams) =>
    request<OrderPage>(`${API_URL}/orders?${query}`, {}, token),
  syncMock: (token: string) =>
    request<{ received: number; created: number; updated: number }>(
      `${API_URL}/orders/mock/sync?count=1000`, { method: 'POST' }, token,
    ),
  batch: (token: string, action: 'audit' | 'print-queue', orderIds: string[]) =>
    request<Record<string, number>>(
      `${API_URL}/orders/batch/${action}`,
      { method: 'POST', body: JSON.stringify({ order_ids: orderIds }) },
      token,
    ),
  importOrders: (token: string, file: File) => {
    const body = new FormData();
    body.append('file', file);
    return request<{ rows: number; created: number; errors: unknown[] }>(
      `${API_URL}/orders/import`, { method: 'POST', body }, token,
    );
  },
};

const agentRequest = <T>(path: string, options: RequestInit = {}) =>
  request<T>(`${AGENT_URL}${path}`, options, AGENT_TOKEN);

export const printAgent = {
  printers: () => agentRequest<Array<{ name: string; is_default: boolean; is_online: boolean }>>('/printers'),
  jobs: () => agentRequest<PrintJob[]>('/jobs'),
  create: (body: object) => agentRequest<PrintJob>('/jobs', { method: 'POST', body: JSON.stringify(body) }),
  retry: (id: string) => agentRequest<PrintJob>(`/jobs/${id}/retry`, { method: 'POST' }),
  preview: async (jobType: string, payload: object) => {
    const response = await fetch(`${AGENT_URL}/preview/${jobType}`, {
      method: 'POST',
      headers: { Authorization: `Bearer ${AGENT_TOKEN}`, 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    });
    if (!response.ok) throw new Error('生成预览失败');
    return response.blob();
  },
};

