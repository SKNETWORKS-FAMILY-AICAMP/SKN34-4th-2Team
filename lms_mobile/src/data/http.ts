import axios, { type AxiosError, type InternalAxiosRequestConfig } from 'axios';

import { useSessionStore } from './sessionStore';

/** LLM 을 거치는 공고 · 코치 · 챗봇이 120초까지 걸린다. Nginx 와 맞춘다. */
export const REQUEST_TIMEOUT = 130_000;

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE || 'http://127.0.0.1:8000/api';
export const WEB_URL = process.env.EXPO_PUBLIC_WEB_URL || 'http://127.0.0.1:5173';

const API_ORIGIN = API_BASE.replace(/\/api\/?$/, '');

/** 로컬 저장소는 `/api/files?t=…` 처럼 상대 주소를 준다 — 앱에서는 서버 주소를 붙여 연다 */
export function absoluteFileUrl(url: string): string {
  return url.startsWith('/') ? `${API_ORIGIN}${url}` : url;
}

export const http = axios.create({
  baseURL: API_BASE,
  timeout: REQUEST_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
});

const raw = axios.create({
  baseURL: API_BASE,
  timeout: REQUEST_TIMEOUT,
  headers: { 'Content-Type': 'application/json' },
});

let refreshFlight: Promise<string> | null = null;

async function requestAccess(): Promise<string> {
  const refresh = useSessionStore.getState().refresh;
  if (!refresh) throw new Error('no refresh token');
  const { data } = await raw.post<{ access: string; refresh?: string }>('/token/refresh', { refresh });
  useSessionStore.getState().setTokens(data.access, data.refresh ?? refresh);
  return data.access;
}

export function refreshAccess(): Promise<string> {
  if (!refreshFlight) {
    refreshFlight = requestAccess().finally(() => {
      refreshFlight = null;
    });
  }
  return refreshFlight;
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
    if (!original || error.response?.status !== 401 || original._retry) throw error;
    if (original.url?.includes('/token/refresh') || original.url?.includes('/login')) throw error;
    original._retry = true;
    try {
      const access = await refreshAccess();
      original.headers = original.headers ?? {};
      original.headers.Authorization = `Bearer ${access}`;
      return http(original);
    } catch (refreshError) {
      if (isAuthRejection(refreshError)) useSessionStore.getState().clear();
      throw refreshError;
    }
  },
);

/** 서버가 토큰을 거절했는지 — 응답이 없는 네트워크 오류는 로그아웃 사유가 아니다 */
export function isAuthRejection(error: unknown): boolean {
  if (error instanceof Error && error.message === 'no refresh token') return true;
  const status = axios.isAxiosError(error) ? error.response?.status : undefined;
  return status === 400 || status === 401 || status === 403;
}

export async function readApiError(error: unknown): Promise<string> {
  if (axios.isAxiosError(error)) {
    const payload = error.response?.data as { detail?: string; message?: string } | undefined;
    if (typeof payload?.detail === 'string') return payload.detail;
    if (typeof payload?.message === 'string') return payload.message;
    if (error.response?.status) return `요청이 실패했습니다 (${error.response.status})`;
  }
  return error instanceof Error ? error.message : '요청이 실패했습니다';
}
