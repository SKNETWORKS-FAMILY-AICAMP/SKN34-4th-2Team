import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

/**
 * 화면 설정 — Flutter `shared/providers/app_appearance_provider.dart`,
 * `side_rail_theme_provider.dart`.
 *
 * 테마 셋(라이트 / 사이드바 다크 / 전체 다크), 사이드바 색 여섯 가지, 밀도 셋.
 * 고른 사이드바 색은 사이드바 바탕뿐 아니라 버튼·링크 색까지 정한다 — 원본도
 * 그렇다(`action`, `actionDark`, `actionLight`). 기기마다 따로 저장된다.
 */
export type ThemeMode = 'light' | 'railDark' | 'dark';
export type Density = 'auto' | 'normal' | 'compact';

export interface RailPalette {
  id: number;
  name: string;
  /** 어두운 사이드바 바탕 */
  background: string;
  border: string;
  /** 사이드바 안에서 선택된 메뉴 글씨 */
  accent: string;
  muted: string;
  /** 밝은 본문의 버튼·링크 — 대비가 확보된 대표색 */
  action: string;
  actionDark: string;
  actionLight: string;
}

/** kSideRailDarkPalettes 그대로 */
export const railPalettes: RailPalette[] = [
  {
    id: 1,
    name: 'Soft Slate',
    background: '#0f172a',
    border: '#1e293b',
    accent: '#38bdf8',
    muted: '#94a3b8',
    action: '#0284c7',
    actionDark: '#0369a1',
    actionLight: '#e0f2fe',
  },
  {
    id: 2,
    name: 'Charcoal',
    background: '#111827',
    border: '#1f2937',
    accent: '#00c2d4',
    muted: '#94a3b8',
    action: '#0891b2',
    actionDark: '#0e7490',
    actionLight: '#cffafe',
  },
  {
    id: 3,
    name: 'Brand Navy',
    background: '#0b2a6f',
    border: '#1e3a8a',
    accent: '#60a5fa',
    muted: '#94a3b8',
    action: '#2563eb',
    actionDark: '#1d4ed8',
    actionLight: '#dbeafe',
  },
  {
    id: 4,
    name: 'Soft Cinematic',
    background: '#0b1224',
    border: '#1e2538',
    accent: '#00c2d4',
    muted: '#94a3b8',
    action: '#7c3aed',
    actionDark: '#6d28d9',
    actionLight: '#ede9fe',
  },
  {
    id: 5,
    name: 'Mid Slate',
    background: '#1e293b',
    border: '#334155',
    accent: '#00c2d4',
    muted: '#cbd5e1',
    action: '#0f766e',
    actionDark: '#115e59',
    actionLight: '#ccfbf1',
  },
  // 푸른 기가 없는 무채색 회색. 2 Charcoal은 이름과 달리 남색에 가깝다.
  {
    id: 6,
    name: 'Graphite',
    background: '#2b2b2b',
    border: '#3a3a3a',
    accent: '#d4d4d4',
    muted: '#a3a3a3',
    action: '#404040',
    actionDark: '#262626',
    actionLight: '#ededed',
  },
];

interface Appearance {
  theme: ThemeMode;
  palette: number;
  density: Density;
  /** 지금 본문이 어두운가 — 화면 코드가 쓰기 쉽게 풀어 둔다. */
  dark: boolean;
  setTheme(next: ThemeMode): void;
  setPalette(next: number): void;
  setDensity(next: Density): void;
}

const AppearanceContext = createContext<Appearance | null>(null);
const KEY = 'lms_react_appearance';

interface Stored {
  theme: ThemeMode;
  palette: number;
  density: Density;
}

function read(): Stored {
  try {
    const raw = window.localStorage.getItem(KEY);
    if (raw !== null) {
      const parsed = JSON.parse(raw) as Partial<Stored>;
      return {
        theme: parsed.theme ?? 'light',
        palette: parsed.palette ?? 1,
        density: parsed.density ?? 'auto',
      };
    }
  } catch {
    /* 무시 */
  }
  return { theme: 'light', palette: 1, density: 'auto' };
}

// ── 색 계산 ───────────────────────────────────────────

function hexToRgb(hex: string): [number, number, number] {
  const v = hex.replace('#', '');
  return [
    parseInt(v.slice(0, 2), 16),
    parseInt(v.slice(2, 4), 16),
    parseInt(v.slice(4, 6), 16),
  ];
}

function luminance(rgb: [number, number, number]): number {
  const [r, g, b] = rgb.map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : Math.pow((s + 0.055) / 1.055, 2.4);
  });
  return 0.2126 * r + 0.7152 * g + 0.0722 * b;
}

function rgbToHsl([r, g, b]: [number, number, number]): [number, number, number] {
  const rr = r / 255;
  const gg = g / 255;
  const bb = b / 255;
  const max = Math.max(rr, gg, bb);
  const min = Math.min(rr, gg, bb);
  const l = (max + min) / 2;
  if (max === min) return [0, 0, l];
  const d = max - min;
  const s = l > 0.5 ? d / (2 - max - min) : d / (max + min);
  const h =
    max === rr
      ? ((gg - bb) / d + (gg < bb ? 6 : 0)) / 6
      : max === gg
        ? ((bb - rr) / d + 2) / 6
        : ((rr - gg) / d + 4) / 6;
  return [h, s, l];
}

function hslToHex(h: number, s: number, l: number): string {
  const f = (n: number) => {
    const k = (n + h * 12) % 12;
    const a = s * Math.min(l, 1 - l);
    const c = l - a * Math.max(-1, Math.min(k - 3, Math.min(9 - k, 1)));
    return Math.round(c * 255);
  };
  return `#${[f(0), f(8), f(4)].map((v) => v.toString(16).padStart(2, '0')).join('')}`;
}

/**
 * 어두운 화면에서 쓸 밝기로 맞춘다 — AppColors._balanced 그대로.
 *
 * 이 색은 어두운 바탕 위의 글씨이면서 흰 글씨를 얹는 바탕이기도 하다. 너무
 * 밝히면 흰 글씨가 사라지고 너무 어두우면 바탕에 묻는다. 상대 휘도 0.18에서
 * 둘 다 견딘다. 색조·채도는 두고 밝기만 이분법으로 찾는다.
 */
function balanced(hex: string, target = 0.18): string {
  const [h, s] = rgbToHsl(hexToRgb(hex));
  let low = 0;
  let high = 1;
  for (let i = 0; i < 24; i++) {
    const mid = (low + high) / 2;
    if (luminance(hexToRgb(hslToHex(h, s, mid))) < target) low = mid;
    else high = mid;
  }
  return hslToHex(h, s, (low + high) / 2);
}

/** 옅은 틴트를 어두운 화면으로 옮긴다 — AppColors.tint와 같은 뜻 */
function tint(hex: string): string {
  const [h, s, l] = rgbToHsl(hexToRgb(hex));
  return hslToHex(h, Math.min(s, 0.5), 0.14 + (1 - l) * 0.1);
}

export function AppearanceProvider({ children }: { children: ReactNode }) {
  const [state, setState] = useState<Stored>(read);

  useEffect(() => {
    const root = document.documentElement;
    const dark = state.theme === 'dark';
    root.dataset.theme = dark ? 'dark' : 'light';
    root.dataset.rail = state.theme === 'light' ? 'light' : 'dark';

    // 밀도 「자동」은 화면 폭을 따른다. 좁은 화면에서 촘촘해진다.
    const resolve = () =>
      state.density === 'auto' ? (window.innerWidth < 1280 ? 'compact' : 'normal') : state.density;
    const apply = () => {
      root.dataset.density = resolve();
    };
    apply();

    const palette = railPalettes.find((p) => p.id === state.palette) ?? railPalettes[0];

    // 사이드바 색
    root.style.setProperty('--rail-dark-bg', palette.background);
    root.style.setProperty('--rail-dark-border', palette.border);
    root.style.setProperty('--rail-dark-accent', palette.accent);
    root.style.setProperty('--rail-dark-muted', palette.muted);

    // 버튼·링크 색. 어두운 화면에서는 밝기를 맞춰 쓴다.
    const primary = dark ? balanced(palette.action) : palette.action;
    const primaryDark = dark ? balanced(palette.actionDark, 0.26) : palette.actionDark;
    root.style.setProperty('--primary', primary);
    root.style.setProperty('--primary-dark', primaryDark);
    root.style.setProperty('--primary-light', dark ? tint(palette.actionLight) : palette.actionLight);

    // 마일리지 카드 바탕 — MileageColors는 primaryDark에서 사이드바 색으로 흐른다.
    root.style.setProperty('--mileage-card-start', primaryDark);
    root.style.setProperty('--mileage-card-end', palette.background);
    root.style.setProperty('--mileage-card-glow', `${primary}59`);

    try {
      window.localStorage.setItem(KEY, JSON.stringify(state));
    } catch {
      /* 무시 */
    }

    if (state.density !== 'auto') return;
    window.addEventListener('resize', apply);
    return () => window.removeEventListener('resize', apply);
  }, [state]);

  const setTheme = useCallback((theme: ThemeMode) => setState((s) => ({ ...s, theme })), []);
  const setPalette = useCallback((palette: number) => setState((s) => ({ ...s, palette })), []);
  const setDensity = useCallback((density: Density) => setState((s) => ({ ...s, density })), []);

  const value = useMemo<Appearance>(
    () => ({
      theme: state.theme,
      palette: state.palette,
      density: state.density,
      dark: state.theme === 'dark',
      setTheme,
      setPalette,
      setDensity,
    }),
    [state, setTheme, setPalette, setDensity],
  );

  return <AppearanceContext.Provider value={value}>{children}</AppearanceContext.Provider>;
}

export function useAppearance(): Appearance {
  const value = useContext(AppearanceContext);
  if (value === null) throw new Error('AppearanceProvider 밖에서 useAppearance를 불렀다');
  return value;
}
