/** 웹 `app/theme.css` 팔레트. 라이트 · 다크만 값이 바뀐다. */
export interface Palette {
  primary: string;
  primaryDark: string;
  primaryLight: string;
  background: string;
  surface: string;
  surfaceVariant: string;
  text: string;
  textSecondary: string;
  textHint: string;
  border: string;
  divider: string;
  success: string;
  warning: string;
  error: string;
  info: string;
  rail: string;
  railFg: string;
  selected: string;
  shadow: string;
}

export const light: Palette = {
  primary: '#0284c7',
  primaryDark: '#0369a1',
  primaryLight: '#e0f2fe',
  background: '#f8f9fb',
  surface: '#ffffff',
  surfaceVariant: '#f3f5f9',
  text: '#111827',
  textSecondary: '#6b7280',
  textHint: '#9ca3af',
  border: '#e5e7eb',
  divider: '#f3f4f6',
  success: '#10b981',
  warning: '#f59e0b',
  error: '#ef4444',
  info: '#3b82f6',
  rail: '#0f172a',
  railFg: '#e2e8f0',
  selected: '#e0f2fe',
  shadow: 'rgba(15, 23, 42, 0.06)',
};

export const dark: Palette = {
  ...light,
  background: '#0f1216',
  surface: '#171a1f',
  surfaceVariant: '#1f232a',
  text: '#e8eaed',
  textSecondary: '#9aa3af',
  textHint: '#6b7280',
  border: '#2a2f37',
  divider: '#232830',
  success: '#34d399',
  warning: '#fbbf24',
  error: '#f87171',
  info: '#60a5fa',
  rail: '#0b0e12',
  railFg: '#cbd2da',
  selected: '#17233d',
};

export const radius = 14;
export const hit = 44;
