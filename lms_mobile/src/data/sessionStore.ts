import * as SecureStore from 'expo-secure-store';
import { create } from 'zustand';

const REFRESH_KEY = 'lms_refresh';
let storageWrite: Promise<void> = Promise.resolve();

function saveRefresh(refresh: string | null): void {
  storageWrite = storageWrite.catch(() => undefined).then(() =>
    refresh ? SecureStore.setItemAsync(REFRESH_KEY, refresh) : SecureStore.deleteItemAsync(REFRESH_KEY),
  );
  void storageWrite.catch(() => undefined);
}

interface TokenState {
  access: string | null;
  refresh: string | null;
  revision: number;
  ready: boolean;
  setTokens: (access: string | null, refresh?: string | null) => void;
  clear: () => void;
  hydrate: () => Promise<void>;
}

export const useSessionStore = create<TokenState>((set, get) => ({
  access: null,
  refresh: null,
  revision: 0,
  ready: false,
  setTokens: (access, refresh) => {
    if (refresh !== undefined) {
      saveRefresh(refresh);
    }
    set((state) => ({
      access,
      refresh: refresh === undefined ? state.refresh : refresh,
      revision: state.revision + 1,
    }));
  },
  clear: () => {
    saveRefresh(null);
    set((state) => ({ access: null, refresh: null, revision: state.revision + 1 }));
  },
  hydrate: async () => {
    if (get().ready) return;
    const revision = get().revision;
    try {
      const refresh = await SecureStore.getItemAsync(REFRESH_KEY);
      set((state) => state.revision === revision
        ? { refresh, ready: true, revision: state.revision + 1 }
        : { ready: true });
    } catch {
      set({ ready: true });
    }
  },
}));
