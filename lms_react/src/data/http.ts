import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { useSessionStore } from './sessionStore';

export const API_BASE =
  (typeof import.meta !== 'undefined' && import.meta.env && import.meta.env.VITE_API_BASE) || '/api';

export const http = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

const raw = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

let refreshFlight: { revision: number; promise: Promise<string> } | null = null;

async function requestAccess(): Promise<string> {
  const { refresh, revision } = useSessionStore.getState();
  if (!refresh) throw new Error('no refresh token');
  const { data } = await raw.post<{ access: string; refresh?: string }>('/token/refresh', { refresh });
  const latest = useSessionStore.getState();
  if (latest.revision !== revision || latest.refresh !== refresh) {
    throw new Error('stale refresh response');
  }
  useSessionStore.getState().setTokens(data.access, data.refresh ?? refresh);
  return data.access;
}

/** 동시에 여러 곳에서 불러도 갱신 요청은 한 번만 보낸다 */
function refreshAccess(): Promise<string> {
  const revision = useSessionStore.getState().revision;
  if (!refreshFlight || refreshFlight.revision !== revision) {
    const flight = { revision, promise: requestAccess() };
    refreshFlight = flight;
    void flight.promise.finally(() => {
      if (refreshFlight === flight) refreshFlight = null;
    }).catch(() => undefined);
  }
  return refreshFlight.promise;
}

http.interceptors.request.use((config) => {
  const access = useSessionStore.getState().access;
  if (access) {
    config.headers = config.headers ?? {};
    config.headers.Authorization = `Bearer ${access}`;
  }
  return config;
});

http.interceptors.response.use(
  (response) => response,
  async (error: AxiosError) => {
    const original = error.config as (InternalAxiosRequestConfig & { _retry?: boolean }) | undefined;
    if (!original || error.response?.status !== 401 || original._retry) {
      throw error;
    }
    if (original.url?.includes('/token/refresh') || original.url?.includes('/login')) {
      throw error;
    }
    original._retry = true;
    const revision = useSessionStore.getState().revision;
    try {
      const access = await refreshAccess();
      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${access}`;
      return http(original);
    } catch (refreshError) {
      if (useSessionStore.getState().revision === revision) useSessionStore.getState().clear();
      throw refreshError;
    }
  },
);

export async function readApiError(error: unknown): Promise<string> {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as { detail?: string; message?: string } | undefined;
    if (typeof payload?.detail === 'string') return payload.detail;
    if (typeof payload?.message === 'string') return payload.message;
    if (error.response?.status) return `요청이 실패했습니다 (${error.response.status})`;
  }
  return error instanceof Error ? error.message : '요청이 실패했습니다';
}

export { refreshAccess };
