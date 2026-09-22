import { create } from 'zustand';

interface TokenState {
  access: string | null;
  refresh: string | null;
  setTokens: (access: string | null, refresh?: string | null) => void;
  clear: () => void;
}

export const useSessionStore = create<TokenState>((set) => ({
  access: null,
  refresh: null,
  setTokens: (access, refresh) =>
    set((state) => ({ access, refresh: refresh === undefined ? state.refresh : refresh })),
  clear: () => set({ access: null, refresh: null }),
}));
