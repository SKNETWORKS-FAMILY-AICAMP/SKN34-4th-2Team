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

let refreshFlight: Promise<string> | null = null;

async function refreshAccess(): Promise<string> {
  const refresh = useSessionStore.getState().refresh;
  if (!refresh) throw new Error('no refresh token');
  const { data } = await raw.post<{ access: string; refresh?: string }>('/token/refresh', { refresh });
  useSessionStore.getState().setTokens(data.access, data.refresh ?? refresh);
  return data.access;
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
    if (!refreshFlight) {
      refreshFlight = refreshAccess().finally(() => {
        refreshFlight = null;
      });
    }
    try {
      const access = await refreshFlight;
      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${access}`;
      return http(original);
    } catch (refreshError) {
      useSessionStore.getState().clear();
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
