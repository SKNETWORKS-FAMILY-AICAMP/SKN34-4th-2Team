import { emptyDb, type Database } from './store';
import { queryClient, queryKeys } from './queryClient';

/** TanStack Query 캐시를 useSyncExternalStore용 스냅샷으로 노출한다. */
export function getBootstrapDb(): Database {
  return queryClient.getQueryData<Database>(queryKeys.bootstrap) ?? emptyDb();
}

export function subscribeBootstrap(onStoreChange: () => void): () => void {
  return queryClient.getQueryCache().subscribe((event) => {
    const key = event?.query?.queryKey;
    if (Array.isArray(key) && key[0] === queryKeys.bootstrap[0]) {
      onStoreChange();
    }
  });
}
