import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

const REFRESH_KEY = 'lms_refresh';

interface TokenState {
  access: string | null;
  refresh: string | null;
  ready: boolean;
  setTokens: (access: string | null, refresh?: string | null) => void;
  clear: () => void;
  hydrate: () => Promise<void>;
}

export const useSessionStore = create<TokenState>((set, get) => ({
  access: null,
  refresh: null,
  ready: false,
  setTokens: (access, refresh) => {
    if (refresh !== undefined) {
      void (refresh
        ? SecureStore.setItemAsync(REFRESH_KEY, refresh)
        : SecureStore.deleteItemAsync(REFRESH_KEY)
      ).catch(() => undefined);
    }
    set((state) => ({
      access,
      refresh: refresh === undefined ? state.refresh : refresh,
    }));
  },
  clear: () => {
    void SecureStore.deleteItemAsync(REFRESH_KEY).catch(() => undefined);
    set({ access: null, refresh: null });
  },
  hydrate: async () => {
    if (get().ready) return;
    try {
      const refresh = await SecureStore.getItemAsync(REFRESH_KEY);
      set({ refresh, ready: true });
    } catch {
      set({ ready: true });
    }
  },
}));
