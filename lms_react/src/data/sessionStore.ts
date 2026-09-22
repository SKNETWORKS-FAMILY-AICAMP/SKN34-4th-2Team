import { create } from 'zustand';

const REFRESH_KEY = 'lms_refresh';

function readRefresh(): string | null {
  if (typeof window === 'undefined') return null;
  try {
    return window.sessionStorage.getItem(REFRESH_KEY);
  } catch {
    return null;
  }
}

interface TokenState {
  access: string | null;
  refresh: string | null;
  setTokens: (access: string | null, refresh?: string | null) => void;
  clear: () => void;
}

export const useSessionStore = create<TokenState>((set) => ({
  access: null,
  refresh: readRefresh(),
  setTokens: (access, refresh) => {
    if (refresh !== undefined) {
      try {
        if (refresh) window.sessionStorage.setItem(REFRESH_KEY, refresh);
        else window.sessionStorage.removeItem(REFRESH_KEY);
      } catch {
        /* ignore */
      }
    }
    set((state) => ({
      access,
      refresh: refresh === undefined ? state.refresh : refresh,
    }));
  },
  clear: () => {
    try {
      window.sessionStorage.removeItem(REFRESH_KEY);
    } catch {
      /* ignore */
    }
    set({ access: null, refresh: null });
  },
}));
