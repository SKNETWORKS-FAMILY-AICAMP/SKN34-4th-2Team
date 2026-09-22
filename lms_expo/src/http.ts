import axios from 'axios';

import { useSessionStore } from './sessionStore';

export const API_BASE = process.env.EXPO_PUBLIC_API_BASE || 'http://127.0.0.1:8000/api';

export const http = axios.create({
  baseURL: API_BASE,
  headers: { 'Content-Type': 'application/json' },
});

http.interceptors.request.use((config) => {
  const access = useSessionStore.getState().access;
  if (access) config.headers.Authorization = `Bearer ${access}`;
  return config;
});
