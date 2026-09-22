import { useQuery } from '@tanstack/react-query';

import { fetchBootstrap } from './bootstrap';
import { queryKeys } from './queryClient';
import { useSessionStore } from './sessionStore';

function isTestMode(): boolean {
  return import.meta.env.MODE === 'test';
}

/** 로그인 후 bootstrap 은 앱에서 한 번만 가져온다. */
export function BootstrapQuery() {
  const access = useSessionStore((state) => state.access);

  useQuery({
    queryKey: queryKeys.bootstrap,
    queryFn: fetchBootstrap,
    enabled: !isTestMode() && Boolean(access),
    staleTime: 30_000,
  });

  return null;
}
