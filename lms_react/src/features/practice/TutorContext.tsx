import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from 'react';

import type { TutorMode } from '../../data/repository';

/** 튜터에게 보낼 지금 모습 — 물을 때마다 새로 읽는다(그 사이 고친 코드 · 새 출력) */
export interface TutorSnapshot {
  code: string;
  run: string;
  grade: string;
}

/** 튜터가 보고 있는 셀 */
export interface TutorTarget {
  cellId: string;
  mode: TutorMode;
  /** 문제 셀 — 원래 세트 · 번호. 다시 풀 문제도 원래 자리로 묻는다(힌트 단계 · 대화가 이어지게) */
  setId?: string;
  index?: number;
  /** 패널 머리 — 「문제 3 · 맥스 풀링」 「셀 2」 */
  label: string;
  read: () => TutorSnapshot;
}

interface Tutor {
  target: TutorTarget | null;
  open: (target: TutorTarget) => void;
  close: () => void;
  /** 튜터 답이 가리킨 줄 — 그 셀 편집기에만 칠한다 */
  marked: { cellId: string; lines: number[] } | null;
  mark: (cellId: string, lines: number[]) => void;
}

const TutorContext = createContext<Tutor | null>(null);

/** 연습장 한 화면에 튜터 하나. 패널 밖(문제 · 코드 셀)의 버튼이 target 을 바꾼다 */
export function TutorProvider({ children }: { children: ReactNode }) {
  const [target, setTarget] = useState<TutorTarget | null>(null);
  const [marked, setMarked] = useState<Tutor['marked']>(null);

  const open = useCallback((next: TutorTarget) => {
    setTarget(next);
    setMarked(null);
  }, []);
  const close = useCallback(() => {
    setTarget(null);
    setMarked(null);
  }, []);
  const mark = useCallback((cellId: string, lines: number[]) => setMarked(lines.length ? { cellId, lines } : null), []);

  const value = useMemo(() => ({ target, open, close, marked, mark }), [target, open, close, marked, mark]);
  return <TutorContext.Provider value={value}>{children}</TutorContext.Provider>;
}

/** 튜터 밖(테스트 · 다른 화면)에서는 null — 버튼을 그리지 않는다 */
export function useTutor(): Tutor | null {
  return useContext(TutorContext);
}

/** 이 셀 편집기에 칠할 줄 */
export function useTutorMarks(cellId: string): number[] | undefined {
  const tutor = useContext(TutorContext);
  return tutor?.marked?.cellId === cellId ? tutor.marked.lines : undefined;
}
