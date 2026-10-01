import { QueryClient, useQuery, useQueryClient } from '@tanstack/react-query';
import { mapBootstrap } from '@web/data/bootstrapMap';
import type { Database } from '@web/data/database';

import { http } from './http';

export const queryKeys = {
  bootstrap: ['bootstrap'] as const,
};

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: { staleTime: 30_000, retry: 1 },
  },
});

export async function fetchBootstrap(): Promise<Database> {
  const { data } = await http.get<Record<string, unknown>>('/bootstrap');
  return mapBootstrap(data);
}

export function useBootstrap() {
  return useQuery({
    queryKey: queryKeys.bootstrap,
    queryFn: fetchBootstrap,
  });
}

export function useDb(): Database | undefined {
  return useBootstrap().data;
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
  const { data } = await http.post<Record<string, unknown>>('/command', { op, payload });
  await queryClient.invalidateQueries({ queryKey: queryKeys.bootstrap });
  return data;
}
