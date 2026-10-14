import AsyncStorage from '@react-native-async-storage/async-storage';
import { createContext, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';
import { useColorScheme } from 'react-native';

import { dark, light, type Palette } from './tokens';

export type ThemeMode = 'light' | 'dark' | 'system';

const KEY = 'lms.theme';

interface ThemeValue {
  mode: ThemeMode;
  palette: Palette;
  setMode: (mode: ThemeMode) => void;
}

const ThemeContext = createContext<ThemeValue | null>(null);

export function ThemeProvider({ children }: { children: ReactNode }) {
  const system = useColorScheme();
  const [mode, setModeState] = useState<ThemeMode>('system');

  useEffect(() => {
    void AsyncStorage.getItem(KEY).then((saved) => {
      if (saved === 'light' || saved === 'dark' || saved === 'system') setModeState(saved);
    });
  }, []);

  const setMode = (next: ThemeMode) => {
    setModeState(next);
    void AsyncStorage.setItem(KEY, next);
  };

  const palette = mode === 'system' ? (system === 'dark' ? dark : light) : mode === 'dark' ? dark : light;
  const value = useMemo(() => ({ mode, palette, setMode }), [mode, palette]);
  return <ThemeContext.Provider value={value}>{children}</ThemeContext.Provider>;
}

export function useTheme(): ThemeValue {
  const theme = useContext(ThemeContext);
  if (theme === null) throw new Error('ThemeProvider 밖에서 useTheme을 불렀다');
  return theme;
}
