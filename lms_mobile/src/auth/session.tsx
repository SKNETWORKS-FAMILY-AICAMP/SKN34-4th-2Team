import { mapUser } from '@web/data/bootstrapMap';
import type { User, UserRole } from '@web/domain/types';
import { createContext, useCallback, useContext, useEffect, useMemo, useState, type ReactNode } from 'react';

import { useSelectedCohort } from '../data/cohort';
import { http, readApiError, refreshAccess } from '../data/http';
import { fetchBootstrap, queryClient, queryKeys, useDb } from '../data/query';
import { useSessionStore } from '../data/sessionStore';

export interface Session {
  user: User | null;
  loading: boolean;
  signIn(
    email: string,
    password: string,
  ): Promise<{ ok: true; role: UserRole; mustChangePassword: boolean } | { ok: false; message: string }>;
  signOut(): Promise<void>;
  changePassword(next: string, current?: string): Promise<{ ok: true } | { ok: false; message: string }>;
  skipPasswordChange(): Promise<{ ok: true } | { ok: false; message: string }>;
}

const SessionContext = createContext<Session | null>(null);

export function homeHref(role: UserRole): '/(student)' | '/(instructor)' | '/(admin)' {
  if (role === 'admin') return '/(admin)';
  if (role === 'instructor') return '/(instructor)';
  return '/(student)';
}

export function SessionProvider({ children }: { children: ReactNode }) {
  const hydrate = useSessionStore((s) => s.hydrate);
  const ready = useSessionStore((s) => s.ready);
  const [uid, setUid] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mustChange, setMustChange] = useState(false);
  const [liveUser, setLiveUser] = useState<User | null>(null);
  const db = useDb();
  const selected = useSelectedCohort(uid ?? undefined);

  useEffect(() => {
    void hydrate();
  }, [hydrate]);

  useEffect(() => {
    if (!ready) return;
    let cancelled = false;
    (async () => {
      const refresh = useSessionStore.getState().refresh;
      if (!refresh) {
        setLoading(false);
        return;
      }
      try {
        if (!useSessionStore.getState().access) await refreshAccess();
        const me = await http.get<Record<string, unknown>>('/me');
        const snapshot = await queryClient.fetchQuery({ queryKey: queryKeys.bootstrap, queryFn: fetchBootstrap });
        if (cancelled) return;
        const nextUid = String(me.data.uid ?? '');
        setUid(nextUid);
        setMustChange(Boolean(me.data.mustChangePassword ?? me.data.must_change_password));
        const found = snapshot.users.find((user) => user.uid === nextUid);
        setLiveUser(
          found ??
            mapUser({ ...me.data, uid: me.data.uid ?? nextUid, firebase_uid: me.data.uid ?? nextUid }),
        );
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
  }, [ready]);

  const signIn = useCallback(async (email: string, password: string) => {
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
      const snapshot = await queryClient.fetchQuery({ queryKey: queryKeys.bootstrap, queryFn: fetchBootstrap });
      setUid(data.uid);
      setMustChange(Boolean(data.mustChangePassword));
      const found = snapshot.users.find((user) => user.uid === data.uid);
      setLiveUser(found ?? (data.user ? mapUser({ ...data.user, uid: data.uid }) : null));
      setLoading(false);
      return { ok: true as const, role: data.role, mustChangePassword: Boolean(data.mustChangePassword) };
    } catch (error) {
      return { ok: false as const, message: await readApiError(error) };
    }
  }, []);

  const signOut = useCallback(async () => {
    setUid(null);
    setMustChange(false);
    setLiveUser(null);
    useSessionStore.getState().clear();
    setTimeout(() => queryClient.clear(), 0);
    void http.post('/logout').catch(() => undefined);
  }, []);

  const changePassword = useCallback(async (next: string, current?: string) => {
    if (next.length < 8) return { ok: false as const, message: '비밀번호는 8자 이상이어야 합니다.' };
    try {
      await http.post('/password', { password: next, currentPassword: current ?? '' });
      setMustChange(false);
      return { ok: true as const };
    } catch (error) {
      return { ok: false as const, message: await readApiError(error) };
    }
  }, []);

  const skipPasswordChange = useCallback(async () => {
    try {
      await http.post('/password', { skip: true });
      setMustChange(false);
      return { ok: true as const };
    } catch (error) {
      return { ok: false as const, message: await readApiError(error) };
    }
  }, []);

  const user = useMemo(() => {
    if (uid === null) return null;
    const found = db?.users.find((item) => item.uid === uid) ?? liveUser;
    if (found === null) return null;
    const signedIn = { ...found, mustChangePassword: mustChange };
    if (signedIn.role !== 'admin' || selected === undefined) return signedIn;
    const cohort = db?.cohorts.find((item) => item.cohortId === selected);
    return cohort === undefined ? signedIn : { ...signedIn, cohortId: cohort.cohortId, cohortName: cohort.name };
  }, [uid, mustChange, liveUser, db, selected]);

  const value = useMemo(
    () => ({ user, loading, signIn, signOut, changePassword, skipPasswordChange }),
    [user, loading, signIn, signOut, changePassword, skipPasswordChange],
  );
  return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
}

export function useSession(): Session {
  const session = useContext(SessionContext);
  if (session === null) throw new Error('SessionProvider 밖에서 useSession을 불렀다');
  return session;
}

export function useCohortId(): string {
  const { user } = useSession();
  return user?.cohortId ?? '';
}
