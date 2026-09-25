import { createContext, useContext, useEffect, useState, type ReactNode } from 'react';
import { Link } from 'react-router-dom';

import { Icon } from '../ui/Icon';

/**
 * 위치 줄(학습실 › 공부방) — 상단 막대 왼쪽에 둔다.
 *
 * 제목 위에 두면 그 화면만 제목이 20px 내려가 다른 화면과 비율이 달라졌다. 상단 막대 왼쪽은
 * 비어 있으므로 거기에 올리고, 시작점은 본문 틀(가운데 1080px)의 왼쪽 끝에 맞춘다.
 * 화면이 `usePageCrumbs` 로 자기 위치를 알리고, 떠나면 지운다.
 */
export interface Crumb {
  label: string;
  /** 없으면 지금 화면 — 글자만 */
  to?: string;
}

const SetCrumbs = createContext<(crumbs: Crumb[]) => void>(() => {});
const Crumbs = createContext<Crumb[]>([]);

export function CrumbsProvider({ children }: { children: ReactNode }) {
  const [crumbs, setCrumbs] = useState<Crumb[]>([]);
  return (
    <SetCrumbs.Provider value={setCrumbs}>
      <Crumbs.Provider value={crumbs}>{children}</Crumbs.Provider>
    </SetCrumbs.Provider>
  );
}

export function usePageCrumbs(crumbs: Crumb[]) {
  const set = useContext(SetCrumbs);
  const key = JSON.stringify(crumbs);
  useEffect(() => {
    set(JSON.parse(key) as Crumb[]);
    return () => set([]);
  }, [set, key]);
}

export function AppbarCrumbs() {
  const crumbs = useContext(Crumbs);
  if (crumbs.length === 0) return null;
  return (
    <nav className="appbar__crumbs" aria-label="위치">
      {crumbs.map((crumb, i) => (
        <span key={`${crumb.label}-${i}`} className="appbar__crumb">
          {i > 0 && <Icon name="chevron_right" size={16} />}
          {crumb.to === undefined ? <span aria-current="page">{crumb.label}</span> : <Link to={crumb.to}>{crumb.label}</Link>}
        </span>
      ))}
    </nav>
  );
}
