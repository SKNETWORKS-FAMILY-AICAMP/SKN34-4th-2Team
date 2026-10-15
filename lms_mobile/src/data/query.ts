import { QueryClient, useQuery, useQueryClient } from '@tanstack/react-query';
import { mapBootstrap } from '@web/data/bootstrapMap';
import type { Database } from '@web/data/database';

import { http, readApiError } from './http';

export const queryKeys = {
  bootstrap: ['bootstrap'] as const,
};

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 60_000, retry: 1 },
  },
});

export async function fetchBootstrap(): Promise<Database> {
  const { data } = await http.get<Record<string, unknown>>('/bootstrap');
  return mapBootstrap(data);
}

/** 앱이 앞에 떠 있는 동안 이 간격으로 다시 받아 새 공지 · 알림이 새로고침 없이 뜨게 한다 */
export const LIVE_REFRESH_MS = 15_000;

export function useBootstrap() {
  return useQuery({
    queryKey: queryKeys.bootstrap,
    queryFn: fetchBootstrap,
    refetchInterval: LIVE_REFRESH_MS,
    refetchIntervalInBackground: false,
  });
}

export function useDb(): Database | undefined {
  return useBootstrap().data;
}

/** 당겨서 새로고침 — Screen 이 끝날 때까지 스피너를 돌린다 */
export function refreshBootstrap(): Promise<void> {
  return queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

export function useInvalidateBootstrap() {
  const client = useQueryClient();
  return () => client.invalidateQueries({ queryKey: queryKeys.bootstrap });
}

/** 쓰기가 끝나기 전에 화면이 옛 값으로 돌아가지 않게 캐시를 먼저 고친다. */
export function patchBootstrap(change: (current: Database) => Partial<Database>): void {
  queryClient.setQueryData<Database>(queryKeys.bootstrap, (prev) => (prev ? { ...prev, ...change(prev) } : prev));
}

export async function runCommand(op: string, payload: Record<string, unknown> = {}): Promise<Record<string, unknown>> {
  let data: Record<string, unknown>;
  try {
    ({ data } = await http.post<Record<string, unknown>>('/command', { op, payload }));
  } catch (error) {
    throw new Error(await readApiError(error));
  }
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
  return data;
}
