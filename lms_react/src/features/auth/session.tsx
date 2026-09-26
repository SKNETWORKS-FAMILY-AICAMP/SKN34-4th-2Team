import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';

import { useSelectedCohortFor } from '../../data/cohortSelection';
import { useCohorts } from '../../data/repository';
import { DemoAccounts } from '../../data/seed';
import { fetchBootstrap, mapUser } from '../../data/bootstrap';
import { http, readApiError, refreshAccess } from '../../data/http';
import { queryClient, queryKeys } from '../../data/queryClient';
import { useSessionStore } from '../../data/sessionStore';
import { getDb } from '../../data/store';
import type { User, UserRole } from '../../domain/types';

const STORAGE_KEY = 'lms_react_session_uid';

export interface Session {
  user: User | null;
  loading: boolean;
  signIn(email: string, password: string): Promise<{ ok: true; role: UserRole; mustChangePassword: boolean } | { ok: false; message: string }>;
  signOut(): Promise<void>;
  changePassword(
    next: string,
    current?: string,
  ): Promise<{ ok: true } | { ok: false; message: string }>;
  skipPasswordChange(): Promise<{ ok: true } | { ok: false; message: string }>;
  switchRole(role: UserRole): void;
}

const SessionContext = createContext<Session | null>(null);

function isTestMode(): boolean {
  return import.meta.env.MODE === 'test';
}

function readStoredUid(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

function resolveLiveUser(
  uid: string,
  users: User[],
  me?: Record<string, unknown>,
): User | null {
  const found = users.find((user) => user.uid === uid);
  if (found !== undefined) return found;
  if (me === undefined) return null;
  return mapUser({
    ...me,
    uid: me.uid ?? uid,
    firebase_uid: me.uid ?? uid,
  });
}

function demoSignIn(email: string, password: string): { ok: true; uid: string } | { ok: false; message: string } {
  const found = getDb().users.find((u) => u.email.toLowerCase() === email.trim().toLowerCase());
  if (found === undefined) {
    return { ok: false, message: '등록되지 않은 이메일입니다.' };
  }
  if (password !== DemoAccounts.password) {
    return { ok: false, message: '비밀번호가 올바르지 않습니다.' };
  }
  if (!found.isActive) {
    return { ok: false, message: '비활성 계정입니다. 관리자에게 문의하세요.' };
  }
  return { ok: true, uid: found.uid };
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const [uid, setUid] = useState<string | null>(() => (isTestMode() ? readStoredUid() : null));
  const [loading, setLoading] = useState(!isTestMode());
  const [mustChange, setMustChange] = useState(false);
  const [liveUser, setLiveUser] = useState<User | null>(null);

  useEffect(() => {
    if (isTestMode()) {
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      const refresh = useSessionStore.getState().refresh;
      if (!refresh) {
        setLoading(false);
        return;
      }
      try {
        if (!useSessionStore.getState().access) await refreshAccess();
        const me = await http.get('/me');
        const db = await queryClient.fetchQuery({ queryKey: queryKeys.bootstrap, queryFn: fetchBootstrap });
        if (cancelled) return;
        const nextUid = String(me.data.uid ?? '');
        setUid(nextUid);
        setMustChange(Boolean(me.data.mustChangePassword ?? me.data.must_change_password));
        setLiveUser(resolveLiveUser(nextUid, db.users, me.data as Record<string, unknown>));
      } catch {
        useSessionStore.getState().clear();
        queryClient.clear();
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (!isTestMode()) return;
    try {
      if (uid === null) window.localStorage.removeItem(STORAGE_KEY);
      else window.localStorage.setItem(STORAGE_KEY, uid);
    } catch {
      /* 테스트만 */
    }
  }, [uid]);

  const signIn = useCallback(async (email: string, password: string) => {
    if (isTestMode()) {
      const result = demoSignIn(email, password);
      if (!result.ok) return result;
      const found = getDb().users.find((u) => u.uid === result.uid);
      setUid(result.uid);
      setMustChange(found?.mustChangePassword ?? false);
      return { ok: true as const, role: found?.role ?? 'student', mustChangePassword: found?.mustChangePassword ?? false };
    }
    try {
      const { data } = await http.post<{
        access: string;
        refresh: string;
        uid: string;
        role: UserRole;
        mustChangePassword: boolean;
        user?: Record<string, unknown>;
      }>('/login', { email: email.trim(), password });
      useSessionStore.getState().setTokens(data.access, data.refresh);
      const db = await queryClient.fetchQuery({ queryKey: queryKeys.bootstrap, queryFn: fetchBootstrap });
      setUid(data.uid);
      setMustChange(Boolean(data.mustChangePassword));
      setLiveUser(resolveLiveUser(data.uid, db.users, data.user));
      setLoading(false);
      return { ok: true as const, role: data.role, mustChangePassword: Boolean(data.mustChangePassword) };
    } catch (error) {
      return { ok: false as const, message: await readApiError(error) };
    }
  }, []);

  const signOut = useCallback(async () => {
    if (!isTestMode()) {
      try {
        await http.post('/logout');
      } catch {
        /* 토큰이 없어도 화면은 나간다 */
      }
      useSessionStore.getState().clear();
      queryClient.clear();
    }
    setUid(null);
    setMustChange(false);
    setLiveUser(null);
  }, []);

  const changePassword = useCallback(async (next: string, current?: string) => {
    if (next.length < 8) {
      return { ok: false as const, message: '비밀번호는 8자 이상이어야 합니다.' };
    }
    if (isTestMode()) {
      setMustChange(false);
      return { ok: true as const };
    }
    try {
      await http.post('/password', { password: next, currentPassword: current ?? '' });
      setMustChange(false);
      return { ok: true as const };
    } catch (error) {
      return { ok: false as const, message: await readApiError(error) };
    }
  }, []);

  const skipPasswordChange = useCallback(async () => {
    if (isTestMode()) {
      setMustChange(false);
      return { ok: true as const };
    }
    try {
      await http.post('/password', { skip: true });
      setMustChange(false);
      return { ok: true as const };
    } catch (error) {
      return { ok: false as const, message: await readApiError(error) };
    }
  }, []);

  const switchRole = useCallback((role: UserRole) => {
    const target = getDb().users.find((u) => u.role === role);
    if (target !== undefined) setUid(target.uid);
  }, []);

  const selectedCohortId = useSelectedCohortFor(uid ?? undefined);
  const cohorts = useCohorts();

  const user = useMemo(() => {
    if (uid === null) return null;
    const found = isTestMode() ? (getDb().users.find((u) => u.uid === uid) ?? null) : liveUser;
    if (found === null) return null;
    const signedIn = { ...found, mustChangePassword: mustChange };
    // 관리자는 상단에서 고른 기수로 본다(Flutter effectiveCohortIdProvider)
    const selected = signedIn.role === 'admin' ? cohorts.find((c) => c.cohortId === selectedCohortId) : undefined;
    return selected === undefined ? signedIn : { ...signedIn, cohortId: selected.cohortId, cohortName: selected.name };
  }, [uid, mustChange, liveUser, cohorts, selectedCohortId]);

  const value = useMemo<Session>(
    () => ({ user, loading, signIn, signOut, changePassword, skipPasswordChange, switchRole }),
    [user, loading, signIn, signOut, changePassword, skipPasswordChange, switchRole],
  );

  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error('SessionProvider 밖에서 useSession을 불렀다');
  return session;
}

export function useCurrentUser(): User {
  const { user } = useSession();
  if (user === null) throw new Error('로그인 없이 보호된 화면에 들어왔다');
  return user;
}
