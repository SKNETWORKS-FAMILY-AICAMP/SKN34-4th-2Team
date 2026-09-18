import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { getDb } from '../../data/store';
import { DemoAccounts } from '../../data/seed';
import type { User, UserRole } from '../../domain/types';

/**
 * 세션 — Flutter의 `authStateProvider` + `currentUserProvider` 자리.
 *
 * 프로토타입에는 Firebase Auth가 없다. 데모 계정 셋의 이메일·비밀번호를 그대로
 * 받고, 로그인 상태만 localStorage에 남긴다.
 */
const STORAGE_KEY = 'lms_react_session_uid';

export interface Session {
  user: User | null;
  loading: boolean;
  signIn(email: string, password: string): { ok: true } | { ok: false; message: string };
  signOut(): void;
  /** 비밀번호 변경 — 프로토타입은 mustChangePassword만 내린다. */
  changePassword(next: string): void;
  switchRole(role: UserRole): void;
}

const SessionContext = createContext<Session | null>(null);

function readStoredUid(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [uid, setUid] = useState<string | null>(readStoredUid);
  const [loading, setLoading] = useState(true);
  const [mustChange, setMustChange] = useState(false);

  useEffect(() => {
    setLoading(false);
  }, []);

  useEffect(() => {
    try {
      if (uid === null) window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, uid);
    } catch {
      /* 저장에 실패해도 이번 세션은 메모리 값으로 돈다 */
    }
  }, [uid]);

  const signIn = useCallback((email: string, password: string) => {
    const found = getDb().users.find(
      (u) => u.email.toLowerCase() === email.trim().toLowerCase(),
    );
    if (found === undefined) {
      return { ok: false as const, message: '등록되지 않은 이메일입니다.' };
    }
    if (password !== DemoAccounts.password) {
      return { ok: false as const, message: '비밀번호가 올바르지 않습니다.' };
    }
    if (!found.isActive) {
      return { ok: false as const, message: '비활성 계정입니다. 관리자에게 문의하세요.' };
    }
    setUid(found.uid);
    setMustChange(found.mustChangePassword);
    return { ok: true as const };
  }, []);

  const signOut = useCallback(() => {
    setUid(null);
    setMustChange(false);
  }, []);

  const changePassword = useCallback(() => setMustChange(false), []);

  /** 시연용 역할 전환. 같은 기수의 다른 역할 계정으로 갈아탄다. */
  const switchRole = useCallback((role: UserRole) => {
    const target = getDb().users.find((u) => u.role === role);
    if (target !== undefined) setUid(target.uid);
  }, []);

  const user = useMemo(() => {
    if (uid === null) return null;
    const found = getDb().users.find((u) => u.uid === uid) ?? null;
    return found === null ? null : { ...found, mustChangePassword: mustChange };
  }, [uid, mustChange]);

  const value = useMemo<Session>(
    () => ({ user, loading, signIn, signOut, changePassword, switchRole }),
    [user, loading, signIn, signOut, changePassword, switchRole],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error('SessionProvider 밖에서 useSession을 불렀다');
  return session;
}

/** 로그인이 보장된 화면에서 쓴다. */
export function useCurrentUser(): User {
  const { user } = useSession();
  if (user === null) throw new Error('로그인 없이 보호된 화면에 들어왔다');
  return user;
}
