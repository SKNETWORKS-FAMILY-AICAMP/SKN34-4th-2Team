import { useCallback } from 'react';

import { registerTarget } from './targetRegistry';

/**
 * 화면 쪽이 타깃을 등록하는 유일한 통로.
 *
 * ```tsx
 * <button ref={useTourTarget(StudentTargets.navBoard)}>게시판</button>
 * ```
 */
export function useTourTarget(targetId: string) {
  return useCallback(
    (el: HTMLElement | null) => registerTarget(targetId, el),
    [targetId],
  );
}
