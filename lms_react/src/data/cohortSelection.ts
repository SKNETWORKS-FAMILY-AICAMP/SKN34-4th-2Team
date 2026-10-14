import { useSyncExternalStore } from 'react';

/**
 * 관리자가 상단에서 고른 기수 — Flutter selectedCohortIdProvider 자리.
 *
 * 관리자는 bootstrap 으로 모든 기수의 데이터를 받는다. 화면은 `user.cohortId` 로 기수를 거르므로,
 * 고른 기수가 있으면 세션이 그 값으로 바꿔 낸다(features/auth/session.tsx). 고른 사람(uid)을 같이 적어
 * 다른 계정으로 로그인하면 쓰지 않는다. 새로고침해도 남도록 브라우저에 둔다.
 */
interface Selection {
  uid: string;
  cohortId: string;
}

const STORAGE_KEY = 'lms.selectedCohort';
const listeners = new Set<() => void>();
let current: Selection | null = read();

function read(): Selection | null {
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    const parsed = raw === null ? null : (JSON.parse(raw) as Partial<Selection>);
    return parsed?.uid && parsed.cohortId ? { uid: parsed.uid, cohortId: parsed.cohortId } : null;
  } catch {
    return null;
  }
}

function write(next: Selection | null): void {
  current = next;
  try {
    if (next === null) window.localStorage.removeItem(STORAGE_KEY);
    else window.localStorage.setItem(STORAGE_KEY, JSON.stringify(next));
  } catch {
    /* 저장이 막혀도 이번 화면에서는 바뀐다 */
  }
  listeners.forEach((listener) => listener());
}

export function selectCohort(uid: string, cohortId: string): void {
  write({ uid, cohortId });
}

export function clearCohortSelection(): void {
  write(null);
}

/** 이 계정이 고른 기수. 고른 적 없거나 다른 계정이 고른 것이면 undefined. */
export function selectedCohortFor(uid: string | undefined): string | undefined {
  return uid !== undefined && current?.uid === uid ? current.cohortId : undefined;
}

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function useSelectedCohortFor(uid: string | undefined): string | undefined {
  const snapshot = useSyncExternalStore(subscribe, () => current);
  return uid !== undefined && snapshot?.uid === uid ? snapshot.cohortId : undefined;
}
